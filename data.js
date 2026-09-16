/* ============================================================
 * Icons Home - 图标数据配置
 *
 * 添加一个图标的步骤（就两步）：
 *   1. 把图片文件放进 icons/ 目录（支持 svg / png / jpg / webp）
 *   2. 在下方 icons 数组里加一条记录，例如：
 *      { "name": "我的应用", "category": "software", "file": "my-app.png", "desc": "可选说明" }
 *
 * 修改分类：改 categories 数组；图标的 category 字段填写分类的 id。
 * ============================================================ */

var ICON_DATA = {
  /* 站点标题，显示在页面顶部 */
  "title": "Icons Home",

  /* 图标 URL 前缀（可选）：
   *  - 留空 ""：点击图标时自动复制「当前页面地址 + icons/文件名」的完整链接
   *  - 填写 CDN 或自定义域名前缀：复制出来的链接会变成「前缀 + icons/文件名」
   *    例如 "https://cdn.example.com/" 或 "https://tanyang88.github.io/Icons-Home/"
   *  - 也可以在网页右上角设置面板里临时修改，保存在浏览器本地 */
  "baseUrl": "",

  /* 分类定义：id 用于数据关联，name 显示在页面顶部的分类栏 */
  "categories": [
    { "id": "software", "name": "软件" },
    { "id": "website",  "name": "网站" },
    { "id": "dev",      "name": "开发" },
    { "id": "media",    "name": "影音" },
    { "id": "game",     "name": "游戏" },
    { "id": "other",    "name": "其他" }
  ],

  /* 图标列表
   *  name     - 显示在图标下方的名称
   *  category - 所属分类 id（必须与 categories 里的 id 一致）
   *  file     - icons/ 目录下的文件名
   *  desc     - 可选，鼠标悬停提示 / 搜索匹配用 */
  "icons": [
    { "name": "示例·软件", "category": "software", "file": "software.svg", "desc": "示例图标，点击卡片即可复制链接" },
    { "name": "示例·网站", "category": "website",  "file": "website.svg",  "desc": "示例图标，点击卡片即可复制链接" },
    { "name": "示例·开发", "category": "dev",      "file": "dev.svg",      "desc": "示例图标，点击卡片即可复制链接" },
    { "name": "示例·影音", "category": "media",    "file": "media.svg",    "desc": "示例图标，点击卡片即可复制链接" },
    { "name": "示例·游戏", "category": "game",     "file": "game.svg",     "desc": "示例图标，点击卡片即可复制链接" },
    { "name": "示例·其他", "category": "other",    "file": "other.svg",    "desc": "示例图标，点击卡片即可复制链接" }
  ]
};
