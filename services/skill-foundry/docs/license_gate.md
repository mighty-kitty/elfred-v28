# License gate

当前 gate：`SIDECAR_ONLY`。

用户已明确本次仅用于次日演示，可复用 FreeTodo 功能且无需因商业协议阻塞。但为了保证后续自研替换和分发判断清晰，本阶段仍执行以下技术 gate：

1. 不修改 `third_party/FreeTodo`。
2. 不直接写 FreeTodo SQLite。
3. 仅调用正式 HTTP API。
4. FreeTodo 前端不改品牌、不嵌入 Elfred 私有代码。
5. 如未来需要修改并分发 FreeTodo 衍生版本，再单独复核许可并切换 gate。
