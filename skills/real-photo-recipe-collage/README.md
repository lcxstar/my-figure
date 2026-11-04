# Real Photo Recipe Skill v3.0 / 真实原图菜谱（六联图固定字体＋封面＋精简写菜谱）

可复用的 6 张原片菜谱步骤图 Skill：保留食材、锅、盘、摆放和原始照片结构，**不使用生成式 AI 重画食物**。输出 3:4 竖版、2 列 × 3 行步骤拼图，统一绿圈编号和底部奶白标签。

## 主要功能

- 以真实锅盘中心为裁剪基准，而不是图片中心；OpenCV 多尺度径向椭圆搜索自动提供外沿候选，支持逐图人工校正。
- 1500×2000 px，步骤标签强制使用 **Noto Sans CJK SC Bold，51px**，编号数字同字族 Bold **49px**；固定绿色、奶白标签和相对位置；无拉伸缩放、轻度自然调色。
- 支持步骤交换、改标题、单张调饱和度，在内存中记录照片 SHA256、裁剪框与自动 QA，诊断报告仅在明确开启时保存。
- **默认只输出最终六联图**，用户无须逐张检查裁剪预览。在内存中自动检查中心偏差、锅沿裁切和标签位置；低置信度自动改用保守构图，在 内存 QA 中记录 `auto_warning`。自动评估不能保证所有照片都完美。

## 快速使用

安装 Python 3.10+、**Noto Sans CJK SC Bold 简体中文粗体** 和 requirements.txt 中的依赖。字体是强制要求，不是推荐：不接受微软雅黑、Noto Sans CJK Regular、Noto Sans CJK JP 或其他默认字体自动替换。把六张原片放入独立 originals/ 文件夹，复制 examples/config.template.json 为自己的 config.json，填写照片路径和步骤文字。运行：

    python -m pip install -r requirements.txt
    python recipe_collage.py --config my_dish/config.json --output my_dish/六联图.png

首次使用**无需人工校准**；程序通过多组锅盘候选和边缘支持度自动选择安全裁剪，完成调色和固定样式后直接输出最终图片。若用户后来发现某格偏移，再定向调整该格的 `subject.center` 与 `radius_fraction`，不用重做其他五格。

## v3.0 字体严格锁定

标准六联图的字体参数固定为：

| 位置 | 字体 | 字重 | 大小 |
|---|---|---|---|
| 六格底部步骤文字 | Noto Sans CJK SC | Bold | 51px |
| 六格左上编号1–6 | Noto Sans CJK SC | Bold | 49px |

- 若使用 `NotoSansCJK-Bold.ttc`，程序通过字体内部元数据自动找到简体中文 SC 字形；标准集合是 **index=2**，绝不会使用默认的日文 JP 字形。
- `font_path` 可指向本机合法安装的字体文件；找不到或字体元数据不匹配，会**直接报错并停止**，绝不会自动替代为微软雅黑、常规体等其他字体。
- 六格字号统一不变，步骤文字太长时需要缩短文案；不会默默缩小字号。生成后内部 QA 保存 font_family、weight、index、path、SHA256 与字号。
- 字体文件**不上传到 GitHub**。跨电脑若要做到完全相同的字形，可在本地 config.json 设置 `required_font_sha256`，强制精确匹配字体文件版本。
- 不论新建、改字、交换图片还是调色，都必须通过同一绘制程序重新渲染最终图片。

本地字体自检（不用上传六张照片）:

```bash
python recipe_collage.py --check-font
# 使用自定义配置时：
python recipe_collage.py --config my_dish/config.json --check-font
```

正常结果应为 `Noto Sans CJK SC`、`Bold`、`font_collection_index=2`（标准 TTC）、`caption_font_px=51`、`number_font_px=49`、`verified=true`。如果没有指定字体，命令将报错而不是替换字体。

## v2.9 全自动终稿模式

默认运行（只生成六联图 PNG）：
```bash
python recipe_collage.py --config my_dish/config.json --output my_dish/六联图.png
```
只向用户展示最终 3:4 六联 PNG，不主动展示六张裁剪预览或 QA 文件。不得通过 AI 生图代替真实原片的裁剪拼接。

- 对每张照片进行多尺度径向对比的椭圆外沿搜索，按原图边缘支持度、圆沿大小、中心偏移评分。
- 裁剪时优先保全锅沿/盘沿、再居中放大，自动避开几何上不可能的“完整圆沿且占画幅95%以上宽度”要求。
- 检测失败时使用真实照片的保守裁剪并记录警告；**不要求用户逐张确认**，也不能声称无误差。
- `--debug` 仅用于技术排错；`--strict` 仅用于主动选择的高级验收，不作为正常出图的步骤。
- 程序内部版本 `3.0-font-locked`；封面图和菜谱文字功能独立不受影响。

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
