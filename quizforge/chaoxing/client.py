"""超星学习通 HTTP 客户端。

基于 ``requests.Session`` 实现账号密码/二维码登录、课程列表、作业列表与
作业题目页抓取。接口地址集中在 ``endpoints`` 模块,解析逻辑集中在
``parser`` 模块,便于单独维护。

登录方式(实测 2026-05 有效):
    * 密码登录:页面隐藏字段 t=true 时,手机号与密码需用固定密钥做
      AES-128-CBC(PKCS7)加密,再 POST /fanyalogin;
    * 二维码登录:GET 登录页取 uuid -> POST /refreshQRCode 取 enc/uuid ->
      展示二维码 -> 轮询 /getauthstatus/v2。
登录成功后 Cookie 会持久化,下次启动自动恢复。

注意:学习通有反爬机制,请合理控制请求频率,仅用于本人账号的作业题目拉取。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from quizforge.chaoxing import endpoints

#: 二维码登录轮询间隔(秒)。
QR_POLL_INTERVAL = 2.0

#: 二维码登录超时(秒)。
QR_LOGIN_TIMEOUT = 120

#: 请求超时(秒)。
REQUEST_TIMEOUT = 15

#: 作业列表最大抓取页数(防御异常页面虚高总页数导致的海量请求)。
_MAX_WORK_PAGES = 100

#: 默认请求头(模拟浏览器,降低被拦截概率)。
DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class ChaoxingError(RuntimeError):
    """学习通相关错误的基类。"""


class LoginRequiredError(ChaoxingError):
    """未登录或登录已失效时抛出。"""


class LoginFailedError(ChaoxingError):
    """账号密码登录失败(账号/密码错误等)。"""


class QrLoginError(ChaoxingError):
    """二维码登录过程中的错误。"""


class FetchError(ChaoxingError):
    """数据拉取失败时抛出。"""


@dataclass
class Course:
    """学习通课程信息。

    Attributes:
        course_id: 课程 id。
        name: 课程名称。
        clazz_id: 班级 id。
        cpi: 个人课程标识(访问课程空间与作业所需)。
    """

    course_id: str
    name: str
    clazz_id: str
    cpi: str


@dataclass
class Work:
    """学习通作业信息。

    Attributes:
        work_id: 作业 id(常规作业为数字,viewWork 类作业为十六进制串)。
        name: 作业名称。
        course_id / clazz_id / cpi: 所属课程信息。
        deadline: 截止时间文本。
        status: 作答状态文本。
        enc: 该作业链接携带的 enc 参数。
        work_answer_id: 已提交作答的 id(未提交时为空)。
        view_id: viewWork 类作业的实例 id(仅 kind=view 时使用)。
        kind: 入口类型,"review" 已批阅回看页、"form" 作答表单页、
            "view" 只读查看页。
    """

    work_id: str
    name: str
    course_id: str
    clazz_id: str
    cpi: str
    deadline: str = ""
    status: str = ""
    enc: str = ""
    work_answer_id: str = ""
    view_id: str = ""
    kind: str = "form"


@dataclass
class CourseSession:
    """进入课程后建立的会话信息。

    Attributes:
        host: 课程空间所在主机(如 https://mooc1-1.chaoxing.com)。
        enc: 课程 enc 参数。
        openc: 课程 openc 参数(嵌在课程主页 JS 中)。
        space_url: 课程主页 URL(作为 Referer)。
    """

    host: str
    enc: str
    openc: str
    space_url: str = ""


class QrLoginContext:
    """一次二维码登录过程的状态。

    Attributes:
        uuid: 二维码标识。
        qr_image_url: 二维码图片地址。
        enc: 二维码加密参数(轮询时需要)。
        started_at: 开始时间戳。
    """

    def __init__(self, uuid: str, qr_image_url: str, enc: str) -> None:
        self.uuid = uuid
        self.qr_image_url = qr_image_url
        self.enc = enc
        self.started_at = time.time()


class ChaoxingClient:
    """学习通 HTTP 客户端。

    Attributes:
        session: 复用的 requests 会话(携带登录 Cookie)。
        cookie_path: Cookie 持久化文件路径。
    """

    def __init__(self, cookie_path: str = "") -> None:
        """初始化客户端。

        Args:
            cookie_path: Cookie 持久化路径;为空时不持久化。
        """
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.cookie_path = cookie_path
        #: 最近一次进入课程所在的主机(作业页须在该主机上请求)。
        self._course_host: str = ""
        self._load_cookies()

    # ------------------------------------------------------------------ #
    # 登录态
    # ------------------------------------------------------------------ #
    @property
    def is_logged_in(self) -> bool:
        """是否已登录(以是否持有 uid 相关 Cookie 判断)。"""
        return bool(self.session.cookies.get("_uid") or
                    self.session.cookies.get("UID"))

    def _load_cookies(self) -> None:
        """从磁盘恢复 Cookie。"""
        if not self.cookie_path or not os.path.isfile(self.cookie_path):
            return
        try:
            with open(self.cookie_path, "r", encoding="utf-8") as fh:
                cookies = json.load(fh)
            self.session.cookies.update(cookies)
        except (json.JSONDecodeError, OSError):
            # Cookie 文件损坏时忽略,用户重新登录即可。
            pass

    def _save_cookies(self) -> None:
        """将当前 Cookie 持久化到磁盘。"""
        if not self.cookie_path:
            return
        cookies = self.session.cookies.get_dict()
        if not cookies:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.cookie_path)),
                    exist_ok=True)
        with open(self.cookie_path, "w", encoding="utf-8") as fh:
            json.dump(cookies, fh, ensure_ascii=False, indent=2)

    def logout(self) -> None:
        """清除本地登录态(Cookie 与持久化文件)。"""
        self.session.cookies.clear()
        if self.cookie_path and os.path.isfile(self.cookie_path):
            os.unlink(self.cookie_path)

    # ------------------------------------------------------------------ #
    # 账号密码登录
    # ------------------------------------------------------------------ #
    def login_with_password(self, phone: str, password: str) -> None:
        """使用手机号 + 密码登录。

        Args:
            phone: 手机号(或学号)。
            password: 登录密码。

        Raises:
            LoginFailedError: 登录失败(账号/密码错误、风控等)。
            ChaoxingError: 网络或流程异常。
        """
        page = self._get_login_page()
        fid = _hidden_value(page, "fid", "-1")
        refer = _hidden_value(page, "refer", endpoints.LOGIN_REFER)
        t = _hidden_value(page, "t", "true")

        if t == "true":
            phone_enc = _aes_encrypt(phone)
            password_enc = _aes_encrypt(password)
        else:
            phone_enc, password_enc = phone, password

        data = {
            "fid": fid,
            "uname": phone_enc,
            "password": password_enc,
            "refer": refer,
            "t": t,
            "forbidotherlogin": _hidden_value(page, "forbidotherlogin", "0"),
            "validate": "",
            "doubleFactorLogin": _hidden_value(page, "doubleFactorLogin",
                                               "0"),
            "independentId": _hidden_value(page, "independentId", "0"),
            "independentNameId": _hidden_value(page, "independentNameId",
                                               "0"),
        }
        try:
            resp = self.session.post(endpoints.PASSWORD_LOGIN, data=data,
                                     timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            result = resp.json()
        except requests.RequestException as exc:
            raise ChaoxingError(f"登录请求失败: {exc}") from exc
        except ValueError as exc:
            raise ChaoxingError("登录接口返回异常,学习通可能改版") from exc

        if not result.get("status"):
            msg = str(result.get("msg2") or result.get("msg") or "登录失败")
            raise LoginFailedError(f"登录失败:{msg}")

        # 跟随落地地址完成登录(设置 uid/fid 等 Cookie)。
        self._follow_login_url(result.get("url") or endpoints.LOGIN_REFER)
        self._save_cookies()

    def _get_login_page(self) -> str:
        """获取登录页 HTML(同时建立会话 Cookie)。"""
        try:
            resp = self.session.get(endpoints.LOGIN_PAGE,
                                    timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ChaoxingError(f"访问登录页失败: {exc}") from exc
        return resp.text

    def _follow_login_url(self, url: str) -> None:
        """访问登录落地地址,补齐跨域 Cookie。"""
        target = urllib.parse.unquote(url)
        try:
            self.session.get(target, timeout=REQUEST_TIMEOUT,
                             allow_redirects=True)
        except requests.RequestException:
            pass  # 该请求失败不影响已获得的登录 Cookie

    # ------------------------------------------------------------------ #
    # 二维码登录
    # ------------------------------------------------------------------ #
    def start_qr_login(self) -> QrLoginContext:
        """发起二维码登录:取 uuid/enc 与二维码图片地址。

        Returns:
            登录上下文(供轮询与展示二维码)。

        Raises:
            QrLoginError: 获取二维码失败。
        """
        page = self._get_login_page()
        uuid = _hidden_value(page, "uuid", "")
        if not uuid:
            raise QrLoginError("登录页未找到 uuid,学习通可能改版了登录流程")
        # 刷新二维码以获取轮询所需的 enc。
        try:
            resp = self.session.post(endpoints.REFRESH_QR,
                                     timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise QrLoginError(f"获取二维码失败: {exc}") from exc
        uuid = str(data.get("uuid") or uuid)
        enc = str(data.get("enc") or "")
        qr_url = (endpoints.PASSPORT_HOST + endpoints.CREATE_QR +
                  f"?uuid={uuid}&fid=-1")
        return QrLoginContext(uuid=uuid, qr_image_url=qr_url, enc=enc)

    def poll_qr_login(self, context: QrLoginContext) -> Dict[str, Any]:
        """轮询一次扫码状态。

        Args:
            context: 登录上下文。

        Returns:
            状态字典:{"done": bool, "ok": bool, "msg": str}。
            done=True 表示登录流程已结束(成功或失败/超时)。

        Raises:
            QrLoginError: 网络异常。
        """
        if time.time() - context.started_at > QR_LOGIN_TIMEOUT:
            return {"done": True, "ok": False, "msg": "二维码已过期,请刷新"}
        try:
            resp = self.session.post(
                endpoints.QR_STATUS,
                data={
                    "enc": context.enc,
                    "uuid": context.uuid,
                    "doubleFactorLogin": "0",
                    "forbidotherlogin": "0",
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise QrLoginError(f"查询登录状态失败: {exc}") from exc

        ok = bool(data.get("status"))
        if not ok:
            return {"done": False, "ok": False,
                    "msg": str(data.get("msg") or "等待扫码...")}
        self._follow_login_url(endpoints.LOGIN_REFER)
        self._save_cookies()
        return {"done": True, "ok": True, "msg": "登录成功"}

    # ------------------------------------------------------------------ #
    # 课程
    # ------------------------------------------------------------------ #
    def get_courses(self) -> List[Course]:
        """拉取当前账号的课程列表。

        Returns:
            课程列表。

        Raises:
            LoginRequiredError: 未登录。
            FetchError: 拉取失败或格式异常。
        """
        self._ensure_login()
        try:
            resp = self.session.get(
                endpoints.COURSE_LIST,
                params={"view": "json", "rss": "1"},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise FetchError(f"获取课程列表失败: {exc}") from exc

        channels = data.get("channelList", []) if isinstance(data, dict) else []
        courses: List[Course] = []
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            content = channel.get("content")
            if not isinstance(content, dict):
                continue
            course_item = _first_item(content.get("course"))
            if not course_item:
                continue
            course_id = str(course_item.get("id") or "")
            clazz_id = str(content.get("id") or "")
            cpi = str(channel.get("cpi") or content.get("cpi") or "")
            if not (course_id and clazz_id and cpi):
                continue
            courses.append(Course(
                course_id=course_id,
                name=str(course_item.get("name") or "未命名课程"),
                clazz_id=clazz_id,
                cpi=cpi,
            ))
        return courses

    # ------------------------------------------------------------------ #
    # 课程会话与作业
    # ------------------------------------------------------------------ #
    def get_works(self, course: Course) -> List[Work]:
        """拉取某课程下的全部作业(自动翻页,多页时逐页抓取)。

        Args:
            course: 课程信息。

        Returns:
            作业列表(已合并所有页)。

        Raises:
            LoginRequiredError: 未登录。
            FetchError: 第一页拉取失败。
        """
        self._ensure_login()
        session_info = self._enter_course(course)
        self._course_host = session_info.host
        params = {
            "classId": course.clazz_id,
            "courseId": course.course_id,
            "isdisplaytable": "2",
            "mooc": "1",
            "ut": "s",
            "enc": session_info.enc,
            "cpi": course.cpi,
            "openc": session_info.openc,
        }
        try:
            resp = self.session.get(session_info.host + endpoints.WORK_LIST,
                                    params=params, timeout=REQUEST_TIMEOUT,
                                    headers={"Referer": session_info.space_url})
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"获取作业列表失败: {exc}") from exc

        from quizforge.chaoxing.parser import parse_total_pages, \
            parse_work_list
        html = _decode(resp.content)
        try:
            works = parse_work_list(html, course)
        except ValueError as exc:
            raise FetchError(str(exc)) from exc

        # 会话失效检测:作业列表为空但页面呈现登录/失效特征时,明确
        # 提示重新登录,而不是静默误报"该课程没有作业"。
        if not works and _looks_like_login_page(html):
            raise LoginRequiredError(
                "学习通登录已失效,请重新登录后再拉取作业")

        # 分页:翻页接口沿用页面 JS 的 changePage URL(无需 openc/cpi)。
        total_pages = min(parse_total_pages(html), _MAX_WORK_PAGES)
        seen_ids = {w.work_id for w in works}
        for page in range(2, total_pages + 1):
            page_params = {
                "courseId": course.course_id,
                "classId": course.clazz_id,
                "pageNum": str(page),
                "isdisplaytable": "2",
                "mooc": "1",
                "ut": "s",
                "enc": session_info.enc,
            }
            try:
                resp = self.session.get(
                    session_info.host + endpoints.WORK_LIST,
                    params=page_params, timeout=REQUEST_TIMEOUT,
                    headers={"Referer": session_info.space_url})
                resp.raise_for_status()
                page_html = _decode(resp.content)
                for work in parse_work_list(page_html, course):
                    # 按 work_id 去重,避免翻页异常/误判时重复入库。
                    if work.work_id not in seen_ids:
                        seen_ids.add(work.work_id)
                        works.append(work)
            except (requests.RequestException, ValueError):
                # 单页翻页失败或为空时跳过,不影响已抓取部分。
                continue
        return works

    def _enter_course(self, course: Course) -> CourseSession:
        """进入课程空间,获取作业接口所需的 host/enc/openc。

        Args:
            course: 课程信息。

        Returns:
            课程会话信息。

        Raises:
            FetchError: 无法进入课程。
        """
        for host in endpoints.MOOC_HOSTS:
            try:
                resp = self.session.get(
                    host + endpoints.COURSE_ENTRY,
                    params={
                        "courseid": course.course_id,
                        "clazzid": course.clazz_id,
                        "vc": "1",
                        "cpi": course.cpi,
                    },
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )
                resp.raise_for_status()
            except requests.RequestException:
                continue
            space_url = resp.url
            enc_match = re.search(r"enc=([0-9a-fA-F]+)", space_url)
            if not enc_match:
                continue
            enc = enc_match.group(1)
            openc_match = re.search(r"openc\s*:\s*'([0-9a-fA-F]+)'",
                                    resp.text)
            if not openc_match:
                continue
            host_match = re.match(r"(https?://[^/]+)", space_url)
            return CourseSession(host=host_match.group(1), enc=enc,
                                 openc=openc_match.group(1),
                                 space_url=space_url)
        raise FetchError("无法进入课程空间,请检查课程权限或稍后重试")

    def get_work_page(self, work: Work) -> str:
        """获取作业题目页 HTML。

        Args:
            work: 作业信息(须包含 enc/kind 等进入课程后获取的字段)。

        Returns:
            页面 HTML 文本(已按正确编码解码)。

        Raises:
            LoginRequiredError: 未登录。
            FetchError: 拉取失败。
        """
        self._ensure_login()
        if work.kind == "review" and work.work_answer_id:
            path = endpoints.WORK_REVIEW_PAGE
            params = {
                "courseId": work.course_id,
                "classId": work.clazz_id,
                "workId": work.work_id,
                "workAnswerId": work.work_answer_id,
                "isdisplaytable": "2",
                "mooc": "1",
                "ut": "s",
                "enc": work.enc,
                "cpi": work.cpi,
            }
        elif work.kind == "view" and work.view_id:
            path = endpoints.WORK_VIEW_PAGE
            params = {
                "id": work.view_id,
                "courseId": work.course_id,
                "classId": work.clazz_id,
                "workId": work.work_id,
                "isdisplaytable": "2",
                "ut": "s",
                "mooc": "1",
                "enc": work.enc,
                "workSystem": "0",
                "cpi": work.cpi,
            }
        else:
            path = endpoints.WORK_FORM_PAGE
            params = {
                "courseId": work.course_id,
                "classId": work.clazz_id,
                "workId": work.work_id,
                "ut": "s",
                "enc": work.enc,
                "cpi": work.cpi,
            }
        host = self._course_host or self._resolve_work_host(work)
        try:
            resp = self.session.get(host + path, params=params,
                                    timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise FetchError(f"获取作业页面失败: {exc}") from exc
        return _decode(resp.content)

    def _resolve_work_host(self, work: Work) -> str:
        """确定作业页所在主机:优先复用进入课程后的主机。

        作业页与作业列表页必须在同一个课程会话主机上访问,否则会返回
        权限错误页。未进入过课程时,尝试用作业信息重新进入课程。
        """
        if self._course_host:
            return self._course_host
        course = Course(course_id=work.course_id, name="",
                        clazz_id=work.clazz_id, cpi=work.cpi)
        try:
            session_info = self._enter_course(course)
            self._course_host = session_info.host
            return session_info.host
        except FetchError:
            return self._find_work_host()

    def _find_work_host(self) -> str:
        """确定作业页所在主机(优先 mooc1,失败时尝试 mooc1-1)。"""
        for host in endpoints.MOOC_HOSTS:
            try:
                resp = self.session.get(host + "/", timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                if resp.status_code == 200:
                    return host
            except requests.RequestException:
                continue
        return endpoints.MOOC_HOSTS[0]

    # ------------------------------------------------------------------ #
    def _ensure_login(self) -> None:
        """确保已登录,否则抛出 LoginRequiredError。"""
        if not self.is_logged_in:
            raise LoginRequiredError("尚未登录学习通,请先完成登录")


# ---------------------------------------------------------------------- #
# 工具函数
# ---------------------------------------------------------------------- #
def _hidden_value(html: str, field_id: str, default: str = "") -> str:
    """从 HTML 中提取指定 id 的隐藏字段值。"""
    match = re.search(
        rf'id="{re.escape(field_id)}"[^>]*value="([^"]*)"', html)
    if match:
        return match.group(1)
    match = re.search(
        rf'value="([^"]*)"[^>]*id="{re.escape(field_id)}"', html)
    return match.group(1) if match else default


def _first_item(holder: Any) -> Optional[Dict[str, Any]]:
    """从 ``{"data": [...]}`` 包装中取出第一个元素。"""
    if isinstance(holder, dict):
        data = holder.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    return None


def _aes_encrypt(plain: str) -> str:
    """AES-128-CBC(PKCS7)加密并输出 Base64。

    密钥同时用作 IV(学习通实现如此)。``pycryptodome`` 未安装时抛出
    ImportError,由调用方提示安装。
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
    except ImportError as exc:
        raise ImportError(
            "账号密码登录需要 pycryptodome,请执行 "
            "pip install pycryptodome(二维码登录无需此库)") from exc
    key = endpoints.AES_TRANSFER_KEY.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, iv=key)
    encrypted = cipher.encrypt(pad(plain.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")


def _decode(content: bytes) -> str:
    """按学习通页面实际编码解码(优先 UTF-8,回退 GBK)。"""
    for encoding in ("utf-8", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _looks_like_login_page(html: str) -> bool:
    """判断页面是否为登录失效/跳转登录的特征页。"""
    markers = ("passport2", "passport.chaoxing", "请重新登录",
               "登录后使用", "您长时间没有操作")
    lowered = html.lower()
    return any(marker in lowered for marker in markers)
