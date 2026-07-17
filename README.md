# GoPro HERO13 多机 Web 控制台

面向 Ego4D 四机采集的本地 Web MVP。当前版本使用模拟设备跑通四机状态、批量开始/停止和时间码同步记录；真实相机接入将通过 Open GoPro COHN 适配器完成。

## 当前功能

- 固定四台 HERO13 的状态面板
- 电量、SD 卡、温度、在线和录制状态
- 全部或指定相机开始/停止录制
- GoPro Labs 动态 UTC 时间码二维码入口
- 时间码扫码完成时间记录
- 每秒刷新设备状态
- 批量命令部分失败反馈

## Docker 启动（推荐）

```bash
./run.sh up
```

打开 `http://localhost:8080`。

常用命令：

```bash
./run.sh dev     # 构建并在前台启动
./run.sh up      # 构建并在后台启动
./run.sh logs    # 查看日志
./run.sh ps      # 查看容器状态
./run.sh down    # 停止服务
./run.sh test    # 运行本地测试和前端构建
```

如需修改 Web 端口：

```bash
GOPRO_WEB_PORT=9000 ./run.sh up
```

## 不使用 Docker 启动

后端：

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

## 验证

```bash
cd backend
uv run pytest

cd ../frontend
npm run test
npm run build
```

## 下一阶段

1. 使用 Open GoPro Python SDK 通过 BLE 完成四台相机首次配对。
2. 将相机配置为 COHN，加入同一个 5GHz 局域网。
3. 新增真实相机适配器，替换 `MockCameraAdapter`。
4. 保存相机序列号、机位和 COHN 凭据。
5. 用真实 HERO13 验证批量命令延迟、断线恢复和幂等性。
