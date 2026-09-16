/* ============================================================
 * Icons Home - 图标数据配置
 *
 * 添加一个图标的步骤（就两步）：
 *   1. 把图片文件放进 icons/ 目录（支持 svg / png / jpg / webp）
 *   2. 在下方 icons 数组里加一条记录：
 *      { "category": "software", "file": "my-app.png", "link": "https://…" }
 *
 * 字段说明：
 *   category - 所属分类 id（必须与 categories 里的 id 一致）
 *   file     - icons/ 目录下的文件名
 *   link     - 可选。点击图标时跳转的自定义网址（新标签页打开），不填则点击图标改为复制链接
 *   name     - 可选。默认不写：图标下方名称自动取文件名（不含扩展名）；
 *              需要与文件名不同的显示名时，才加这个字段覆盖
 *
 * 分类：编辑 categories 数组即可自定义分类名称、添加或删除分类。
 *   每个分类一行：{ "id": "唯一标识", "name": "显示的分类名" }
 * ============================================================ */

var ICON_DATA = {
  /* 站点标题，显示在页面顶部 */
  "title": "Icons Home",

  /* URL 前缀（推荐留空）：
   *  - 留空 ""：自动匹配当前部署环境。
   *    本地双击打开 → 复制 file:// 完整链接；nginx 部署在 http://服务器/ → 复制 http://服务器/…；
   *    外网 https://域名/ → 复制 https://域名/…，换环境无需改代码。
   *  - 填写 CDN 或固定域名：强制使用「前缀 + icons/文件名」。
   *  - 也可在网页右上角「设置」面板临时修改，保存在浏览器本地。 */
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

  /* 图标列表：
   *   - 名称自动取文件名（不含扩展名），一般不需要写 name
   *   - link 为占位示例，替换成你自己的地址 */
  "icons": [
    { "category": "software", "file": "software.svg", "link": "https://example.com/software" },
    { "category": "website",  "file": "website.svg",  "link": "https://example.com/website" },
    { "category": "dev",      "file": "dev.svg",      "link": "https://example.com/dev" },
    { "category": "media",    "file": "media.svg",    "link": "https://example.com/media" },
    { "category": "game",     "file": "game.svg",     "link": "https://example.com/game" },
    { "category": "other",    "file": "other.svg" }
  ]
};
