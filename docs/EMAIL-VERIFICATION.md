# 邮箱验证码接入

Elfred 已接入邮箱注册验证码：发送请求进入 Resend，6 位验证码 10 分钟有效，同一邮箱 1 分钟内不能重发，连续输错 5 次后需重新获取。验证成功才为新邮箱账号记录“已验证”。原有密码登录不变；旧账号不会仅凭收到该邮箱的验证码就被接管。

上线前仍须在 Resend 控制台验证自有发件域名，并把 `ELFRED_RESEND_API_KEY`、`ELFRED_EMAIL_FROM` 写入服务器私有 `.env.local`（模板：[email.env.example](../config/email.env.example)）。公网入口还需 HTTPS；本机 `localhost` 可以用 HTTP 测试。建议同时配置 `ELFRED_EMAIL_CODE_SECRET`。重启服务后，`GET /api/elfred/auth/email/status` 应返回 `configured: true`；再用本人可接收邮件的邮箱完成一次注册测试，确认服务商接收、邮箱实际收到、验证码可用。仅有模型 API Key、服务器上的 Postfix 程序或网页构建环境都不能证明邮件可投递。

未配置发件服务时，页面明确提示邮箱未验证，保留原有密码注册；后台不会声称已发送验证码。配置后，新邮箱注册必须提交邮件验证码。注册成功使用原邮箱加原密码登录会进入同一账号。旧账号仍可用原密码登录，但不会自动变成“邮箱已验证”。
