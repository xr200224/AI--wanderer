# Render 部署步骤

## 1. 上传到 GitHub

不要上传 `.env`。项目已经通过 `.gitignore` 忽略 `.env` 和本地缓存文件。

```bash
cd "/Users/xu/Desktop/AI旅行助手 15.43.22"
git init
git add .
git commit -m "Deploy AI Wanderer to Render"
git branch -M main
git remote add origin 你的GitHub仓库地址
git push -u origin main
```

## 2. 在 Render 创建服务

推荐方式：Render Dashboard -> New -> Blueprint -> 选择这个 GitHub 仓库。

Render 会读取 `render.yaml`，创建一个 Python Web Service。

## 3. 填写环境变量

创建 Blueprint 时，Render 会要求填写：

```text
RAPIDAPI_KEY=你的RapidAPI密钥
```

不要把密钥写到 `index.html`、`render.yaml` 或 GitHub。

## 4. 访问线上地址

部署完成后打开：

```text
https://你的-render-service.onrender.com/index.html
```

前端会自动调用同域名下的 `/api/...`，不再使用本地 `127.0.0.1`。

## 5. 常见问题

- 如果 TripAdvisor 数据为空，检查 Render 环境变量里是否填写了 `RAPIDAPI_KEY`。
- 如果页面还请求本地地址，在浏览器控制台清除 `localStorage.tripadvisorProxyBase`。
- 免费实例可能会冷启动，第一次打开会慢一些。
