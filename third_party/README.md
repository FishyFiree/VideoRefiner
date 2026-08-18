# third_party — Vendored 组件说明

本项目 vendored（随仓库分发、锁定版本）以下上游代码，均保持上游原样：

## ECCV2022-RIFE（`ECCV2022-RIFE/`）

- 来源：https://github.com/hzwer/ECCV2022-RIFE（MIT License）
- 锁定 commit：`5d8adbdd40e12c2c8f91930eff838aebe561c086`
- 用途：提供 `model/` 包（warplayer 光流算子、loss 等底层模块）
- 已精简：仅保留运行时需要的 `model/` 包 + LICENSE + README（移除训练/演示代码）
- **本地改动**：`model/loss.py` 顶部 `import torchvision.models` 改为 `VGGPerceptualLoss`
  内的惰性导入（torchvision 仅训练用；避免推理与打包引入 torchvision/PIL/opencv）

## RIFE v4.26 官方模型包（`RIFE-v4.26/`）

- 来源：https://huggingface.co/hzwer/RIFE 的 `RIFEv4.26_0921.zip`
- zip SHA256：`1FA9B9CDA3D9B8C3E301359E2595960902F97BF926C08598B0E9957A3F3F760E`
- 内容：`RIFE_HDv3.py`（Model 类）+ `train_log/IFNet_HDv3.py`（IFNet 架构，与 v4.26 权重匹配）
- 说明：模型权重（`rife4.26.pkl`，约 15MB）**不随仓库分发**——应用首次运行自动从
  HuggingFace 镜像下载到 `%APPDATA%/VideoRefiner/models/`；也可手动放置到该目录实现离线使用。
