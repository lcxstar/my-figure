# Real Photo Recipe Skill v2.8 / 真实原图菜谱（六联图＋封面图＋精简写菜谱）

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
## v2.6 制作封面图：盘/碗优先定位、移除手与背景

封面处理独立于六联图：六联图 recipe_collage.py 不变。

1. 把原始照片路径写入 `examples/cover.config.template.json` 的本地副本，默认 `mask.mode=auto_plate`。程序先识别白盘/白碗的**实际外沿**，拟合椭圆中心，手和食物重心都不参与定位。不能对新照片套用旧照片的固定椭圆坐标。
2. 如果检测不到可信的完整碗盘，程序明确失败；此时使用原片同尺寸的 `mask.mode=alpha_file` 手工确认蒙版，不生成食物或补全缺失盘沿。
3. 先分离盘碗主体和手，再将经确认的盘碗外框中心对准最终 3:4 画布中心（默认宽 86%），只替换背景为浅灰布纹+极淡植物花纹；支持真实桌布照片。
4. 调色最后进行，默认亮度 1.035、对比 1.035、饱和度 1.045、锐度 1.035。
5. 输出 `封面图.png`、`封面图_QA.json` 和 `封面图_QA_rim_preview.png`。QA 预览展示**原片中的真实检测外沿和中心**，必须目视确认没有切盘沿、露手、错误居中；机器值通过不代表视觉验收。

运行：
```bash
python -m pip install -r requirements.txt
python cover_photo.py --config examples/cover.config.template.json
```

涉及个人照片的原图、蒙版和生成结果只留本地，不上传公开仓库。

## v2.8 写菜谱（默认精简）

输入菜名、食材和实际操作（可加照片），说“写菜谱”或“按照菜谱 Skill 写步骤”，即使用统一文案格式：

```text
准备食材
食材及实际使用的调味料。

步骤
1. 第一步真实操作。
2. 第二步真实操作。
3. 继续按实际过程编号。
```

默认5–7步、每步约20–45字，尽量每步一句，语言稍口语化；完整保留真实顺序、关键火候、时间和食材比例，不推测未明确的调味料和用量。每一步不加四字小标题，**不输出技巧、心得、总结、制作感受及任何额外段落**。真实工序需要更多或更少步骤时不强行凑数；图片六联图与菜谱文字的步骤数量不必完全相同，除非用户要求一一对应。详细触发、修订和证据规范见 [references/recipe-writing.md](references/recipe-writing.md)。此子功能是写作指令，无须安装新 Python 依赖，不影响已有两个图像功能。
