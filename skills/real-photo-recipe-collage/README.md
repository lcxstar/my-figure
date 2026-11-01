# Real Photo Recipe Collage / 真实原片菜谱六联图

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