// 第二页/第四页的数据层入口（页面一直从这里取，所以名字没变）。
//
//   pages24-view-data.ts → 视图数据 + 演示兜底（只读）
//   pages24-live.ts      → 真数据就地替换（唯一会改那些常量的地方）
//
// 这里 import 一次 `pages24-live` 是为了它的副作用：把"快照 → 视图"的替换注册进去。
export * from "./pages24-view-data";
import "./pages24-live";
