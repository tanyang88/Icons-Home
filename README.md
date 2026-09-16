# Icons Home

一个纯静态的个人图标收藏网页：把图标图片放进 `icons/` 目录，在 `data.js` 里加一条记录，点击图标即可复制图标链接，用于 NAS、导航页或其它网页展示。

参考 [Siriling/my-icons](https://github.com/Siriling/my-icons) 的交互思路，从零实现为**零依赖、无需构建**的纯静态版本。

## 特性

- 纯静态：单页 HTML + 一个数据文件，双击 `index.html` 即可本地使用，无需安装 Node、无需服务器
- 分类浏览：顶部分类栏按分类筛选，自动统计每个分类的图标数量
- 搜索：按图标名称和描述实时过滤
- 一键复制：点击任意图标卡片，复制该图标的完整 URL 到剪贴板
- URL 前缀设置：页面右上角「设置」面板可填写 CDN 或自定义域名前缀，复制出的链接自动带上该前缀
- 深色主题、响应式布局，手机电脑都能用

## 目录结构

```
Icons-Home/
├── index.html   # 页面本体（样式和逻辑都在里面，一般不用改）
├── data.js      # 图标数据配置：分类、图标清单、URL 前缀（日常主要改这个）
├── icons/       # 图标图片目录：把图片丢进来即可
└── README.md
```

## 如何添加一个图标

只要两步：

1. 把图片文件放进 `icons/` 目录（支持 `svg` / `png` / `jpg` / `webp`，推荐正方形 512×512 左右）
2. 在 `data.js` 的 `icons` 数组里加一条记录：

```js
{ "name": "我的应用", "category": "software", "file": "my-app.png", "desc": "可选说明" }
```

- `name`：图标下方显示的名称
- `category`：所属分类 id，必须与 `categories` 里的 `id` 一致
- `file`：`icons/` 目录下的文件名
- `desc`：可选，鼠标悬停提示，也会参与搜索匹配

改完保存，刷新页面即可看到新图标。

## 如何调整分类

修改 `data.js` 里的 `categories` 数组即可：

```js
"categories": [
  { "id": "software", "name": "软件" },
  { "id": "mycat",    "name": "我的分类" }
]
```

图标的 `category` 字段填写对应的 `id`。分类栏会自动按此渲染。

## 本地打开

直接双击 `index.html` 用浏览器打开即可，不需要启动任何服务。

## 设置图标链接前缀

页面右上角「设置」面板可填写 URL 前缀，例如：

- 留空：复制出「当前页面地址 + icons/文件名」的完整链接
- 填写 `https://cdn.example.com/`：复制出 `https://cdn.example.com/icons/文件名`
- 填写 `https://tanyang88.github.io/Icons-Home/`：复制出 Pages 在线地址

设置保存在浏览器本地（localStorage），换浏览器需要重新设置；「恢复默认」可回到 `data.js` 里 `baseUrl` 的值。

## 部署到 GitHub Pages（可选）

把仓库推到 GitHub 后，在仓库 Settings → Pages 中：

1. Source 选择 `Deploy from a branch`
2. Branch 选择 `main`，目录选择 `/ (root)`
3. 保存后等待一两分钟，访问 `https://<用户名>.github.io/Icons-Home/` 即可

在线使用时图标链接复制的是 Pages 地址，可以直接用于 NAS、导航页等场景。

## License

[MIT](./LICENSE)
