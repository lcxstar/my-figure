# Real Photo Recipe Skill v2.4 / 真实原图菜谱（六联图＋封面图）

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
## v2.4 原图保真封面模式

命令：python cover_photo.py --config examples/cover.config.template.json

- 只使用真实照片像素进行抠图、等比缩放、居中和轻调色；禁止生成式重绘，禁止凭空补食物或盘沿。
- 默认 1200×1600 竖版封面；统一纯色浅灰背景 #C8C8C3，配白色盘子较为清爽，不会压得太暗。
- 默认调色：亮度/对比/饱和度各 1.025，锐度 1.03；可以修改配置，但不建议超过保真界限。
- 首次处理需要根据原图调整蒙版位置。规则碗盘可以用 ellipse 蒙版进行近似预览，边缘不规则时需要同尺寸黑白 alpha_file 蒙版。
- 去手只去除主体以外的手。手遮住盘沿时不能无损恢复，必须明确报告限制，不得为了美化而重画。
- 每张图片写入源文件 SHA256 和 _QA.json；默认 review_required，需人工确认盘沿、手、主体形状和背景。
- 六联图原有 recipe_collage.py 仍独立使用，未改变既有排版算法。
