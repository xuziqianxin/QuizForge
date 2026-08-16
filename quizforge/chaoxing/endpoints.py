"""超星学习通接口地址常量。

学习通平台可能调整接口,维护时只需修改本文件中的地址即可,业务代码
无需改动。

接口基于 2026 年实测校准(2026-05):
    * 登录域:  https://passport2.chaoxing.com(当前有效)
    * 课程域:  https://mooc1-api.chaoxing.com
    * 课程空间: https://mooc1.chaoxing.com / https://mooc1-1.chaoxing.com
                (进入课程后由服务端重定向决定,可能为 mooc1-N)
"""

# ---------------------------------------------------------------------- #
# 登录相关
# ---------------------------------------------------------------------- #
#: 登录页(PC 网页版),响应 HTML 中包含二维码 uuid / enc 与表单隐藏字段。
PASSPORT_HOST = "https://passport2.chaoxing.com"
LOGIN_PAGE = PASSPORT_HOST

#: 刷新二维码(POST),参数无,返回 JSON:{"enc": ..., "uuid": ...}。
REFRESH_QR = PASSPORT_HOST + "/refreshQRCode"

#: 二维码图片地址(相对 PASSPORT_HOST),参数 uuid/fid。
CREATE_QR = "/createqr"

#: 轮询扫码状态(POST),参数 enc/uuid/doubleFactorLogin/forbidotherlogin。
QR_STATUS = PASSPORT_HOST + "/getauthstatus/v2"

#: 账号密码登录(POST),参数见 client.login_with_password。
PASSWORD_LOGIN = PASSPORT_HOST + "/fanyalogin"

#: 登录成功后的落地地址(使用 HTTPS,避免会话 Cookie 明文传输)。
LOGIN_REFER = "https://i.mooc.chaoxing.com"

#: 密码登录的 AES 传输密钥(实测 2026-05 有效)。
AES_TRANSFER_KEY = "u2oh6Vu^HWe4_AES"

# ---------------------------------------------------------------------- #
# 课程相关
# ---------------------------------------------------------------------- #
MOOC_API_HOST = "https://mooc1-api.chaoxing.com"

#: 我的课程列表(JSON),参数 view=json&rss=1。
COURSE_LIST = MOOC_API_HOST + "/mycourse/backclazzdata"

#: 课程空间入口(进入后重定向到课程主页,并携带 enc 参数)。
#: 课程主页 JS 中另有 openc 字段,两者是拉取作业的必要参数。
COURSE_ENTRY = "/visit/stucoursemiddle"

# ---------------------------------------------------------------------- #
# 作业相关
# ---------------------------------------------------------------------- #
MOOC_HOSTS = ("https://mooc1.chaoxing.com", "https://mooc1-1.chaoxing.com")

#: 作业列表(HTML),参数 classId/courseId/isdisplaytable/mooc/ut/enc/cpi/openc。
WORK_LIST = "/mooc-ans/work/getAllWork"

#: 作业题目页-已批阅回看(HTML),含"正确答案/我的答案"。
WORK_REVIEW_PAGE = "/mooc-ans/work/selectWorkQuestionYiPiYue"

#: 作业题目页-只读查看(HTML),过期/未交作业使用。
WORK_VIEW_PAGE = "/mooc-ans/work/viewWork"

#: 作业题目页-作答表单(HTML),含输入控件,题目无标准答案。
WORK_FORM_PAGE = "/mooc-ans/work/doHomeWorkNew"
