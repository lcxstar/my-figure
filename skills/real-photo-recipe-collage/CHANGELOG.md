# Change log

## v2.4 · 2026-11-01

- 新增封面图功能（cover_photo.py），以原片真实像素抠图、等比例居中、统一浅灰背景 #C8C8C3、轻度调色。
- 新增 examples/cover.config.template.json、tests/test_cover_photo.py。
- 禁止生成式重绘食物、盘子、碗、锅、缺失盘沿或装饰。手遮挡盘沿时不做凭空补画。
- 输出原片 SHA256 与 _QA.json，初始 review_required。
- 保留原 v2.2 六联图算法和文字排版不动。
