# Real Photo Recipe Skill v2.5 / 真实原图菜谱（六联图＋封面图）

可复用的 6 张原片菜谱步骤图 Skill：保留食材、锅、盘、摆放和原始照片结构，**不使用生成式 AI 重画食物**。输出 3:4 竖版、2 列 × 3 行步骤拼图，统一绿圈编号和底部奶白标签。

## 主要功能

- 以真实锅盘中心为裁剪基准，而不是图片中心；OpenCV HoughCircles 仅做初步候选，支持逐图人工校正。
- 1500×2000 px，固定标签字体/颜色/相对位置；无拉伸缩放、轻度自然调色。
- 支持步骤交换、改标题、单张调饱和度，保留照片 SHA256、裁剪框与 QA 报告。
- 新图片默认 review_required，程序检测不能替代目视核验。

## 快速使用

安装 Python 3.10+、中文字体（建议本机安装 Noto Sans CJK Bold）和 requirements.txt 中的依赖。把六张原片放入独立 originals/ 文件夹，复制 examples/config.template.json 为自己的 config.json，填写照片路径和步骤文字。运行：

    python -m pip install -r requirements.txt
    python recipe_collage.py --config my_dish/config.json --debug

首次使用要检查裁剪预览，发现偏移后修改该张步骤的 subject.center 与 radius_fraction，不要依赖未经确认的检测候选。

## 分享注意

公开版本不包含用户私人菜谱原片、厨房照片、个人文件路径、生成结果或字体文件。照片仍归照片所有者。仓库原有 MIT License 适用。本 Skill 存在于公开仓库 lcxstar/my-figure 的独立目录，可单独复制为新仓库。
## v2.5 制作封面图：原图保真、居中、浅灰植物纹桌布

本模式与六联图独立：旧六联图脚本 recipe_collage.py 不变。

1. 把一张原始美食照片与可校验的蒙版写入 examples/cover.config.template.json 的副本。盘/碗完整保留，去手仅删除主体外背景；若手压住盘沿，不进行生成式补画。
2. 基于前景蒙版非透明外接框居中，默认画布 1200×1600（3:4）；主体宽 86%，左右留白均衡。注意：蒙版须对准真实碗盘外缘，默认 ellipse 只是候选。
3. 背景默认使用浅灰布纹与非常淡的植物花纹（linen_botanical, #D0D0CB），也支持 background.mode=image 并指向真实拍摄的桌布图片，以得到真正的照片级布料质感。背景花纹只出现在主体之外。
4. 默认轻调色：brightness=1.035、contrast=1.035、saturation=1.045、sharpness=1.035。可针对用户反馈单独调整。
5. 接触阴影默认 contact_shadow=0.10，只加在背景，不改原菜像素的构图或形状。
6. 输出 PNG 与 _QA.json：记录蒙版 bbox、画布中心误差、背景来源、原片 SHA256 与调色。程序误差为零也不能替代目视检查，新照片必须人工核对。

执行：

    python -m pip install -r requirements.txt
    python cover_photo.py --config examples/cover.config.template.json

兼容旧版纯灰背景配置，例如 background="#C8C8C3"。真实用户照片、背景素材、运行结果不纳入公开仓库。
