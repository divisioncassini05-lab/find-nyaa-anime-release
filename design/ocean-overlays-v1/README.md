# 水下独立贴图 · 设计稿

本目录保留素材设计原稿。精选素材已压缩并接入仓库内 DSH 页面，未替换安装版、未发布。原有白天/夜晚地形保持不变。
全部 PNG 使用内置 image_gen 生成并保留透明通道；没有使用 CLI 图像生成后备方案。
`index.html` 可以直接打开，对照同一贴图叠在白天、夜晚背景上的效果。

## 素材

| 文件 | 用途 | 密度约束 |
| --- | --- | --- |
| `fish-silver.png` | 银蓝色小鱼群 | 三只为一组 |
| `fish-gold.png` | 浅金短身鱼 | 两只为一组 |
| `fish-jade.png` | 青绿细身鱼 | 三只为一组 |
| `whale-easter-egg.png` | 蓝背、奶白肚皮、弯眼的彩蛋小鲸鱼 | 偶尔单只出现，不替换女孩角色 |
| `jellyfish-night.png` | 远景月光水母 | 两只为一组，夜间边缘点缀 |
| `jellyfish-lantern.png` | 可独立移动的提灯水母 | 单只，供以后女孩照明使用 |
| `bubble-trail.png` | 五个稀疏气泡 | 透明内部，薄泡壁，不含雾状底色 |
| `current-traces.png` | 微弱洋流细纹 | 低透明度环境底噪，不做明显流线 |

鱼群是备选，不是同时出现清单。页面一次只出现一小组，避开文字和主要操作区域。
当前文件是高分辨率设计原图，页面使用 `assets/ocean/overlays/` 中的小尺寸 WebP，不直接加载这些原图。

## 提灯水母的可复用发光

按用户最新决定，只实现水母自身的照明效果，后续复用即可。不另做女孩受光遮罩、距离感应或照明交互系统。
这里未来提到的小鲸鱼角色指女孩，不是 `whale-easter-egg.png` 中的动物彩蛋。

- 本体使用 `jellyfish-lantern.png` 的 WebP 版本，珍珠白亮芯、浅青边缘。
- `JellyfishLight` 组件在本体后叠加同源、局部遮罩的轻微模糊光层，光只围绕伞盖，不覆盖页面。
- 夜间只出现一只，远景双水母保留为设计备选，避免堆叠。
- 发光随本体一起移动，无需额外轮询或计算女孩位置；不修改女孩、座位或背景颜色。
- 关闭动态后仍保留稳定的轻微发光；减少动态或页面不可见时停止动画。

## 提示词设计要点

共同要求：透明 PNG、独立叠加素材、手绘二次元水下风格、干净边缘，无文字/边框/场景；不改变固定背景。

- 银蓝小鱼：三只银蓝色小鱼，错落右游，淡色鳍、简洁轮廓，稀疏小组。
- 浅金短身鱼：两只浅金杏色短身鱼，朝左，柔和浅桃条纹与淡青鳍，不使用高饱和热带配色。
- 青绿细身鱼：三只细长青绿小鱼，向右上游，远景感，轻淡、简化细节。
- 彩蛋小鲸鱼：参考用户蓝色圆滚滚鲸鱼图片，蓝背、奶白肚皮、弯眼，柔软布偶般的动画质感；没有配饰，无外部大光晕。
- 远景水母：两只珍珠白/浅青/淡紫月光水母，半透明伞盖、细软触须，主要用于夜景。
- 气泡最终修订：保留五个气泡的位置与大小，移除连接它们的雾、灰色底色与青色水洗，只保留断续薄泡壁和短高光，内外完全透明。
- 洋流：稀疏细浅 S 形纹理和极少细点，用作微弱环境底噪，不产生明显光带。

### 提灯水母最终提示词

Use case: stylized-concept. Asset type: standalone transparent PNG sprite for a hand-painted anime underwater interface. Input image is STYLE REFERENCE ONLY. Create ONE new solitary moon jellyfish that can later serve as a small living lantern beside a girl character. Do not include any girl or other creature in this image. Preserve the reference's gentle translucent pearl-blue/lavender palette and delicate anime paint, but simplify detail for legibility at 80-120 pixels tall. One softly rounded dome seen from front and slightly below, a subtly luminous pearl-white four-petal core inside, a thin pale aqua rim, 4-6 graceful short trailing filaments, two small translucent frilled arms. Compact elegant silhouette, no face, no accessories, no decorations. Warm pearl-white core, cool pale turquoise edge, just a hint of lilac on the lower frill. Light is represented ONLY by painted bright internal details; do NOT bake a diffuse halo, fog, bloom, light rays, cast light, background wash or shadows outside the silhouette. That light will be composited in code later. Entire single jellyfish centered, fully visible with generous transparent margin all around, softly inclined to the left. Flat cel-painted/anime watercolor rendering, NOT realistic gelatin, NOT 3D, NOT neon. All outside pixels truly alpha transparent, preserve partial transparency inside the animal. No text, no border, no scene, no seabed, no bubbles. Deliver a clean, independent lantern-jellyfish cutout.
