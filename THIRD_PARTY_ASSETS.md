# Artwork and third-party notices

## Denia fan artwork

`apps/web/public/art/denia-twilight.png` is AI-generated, unofficial fan artwork of **達妮婭 / Denia** from **鳴潮 / Wuthering Waves**, created for this project with the built-in image generation tool. It replaces the original home hero, login panel and guide illustration. The generation prompt is recorded in [the artwork README](apps/web/public/art/README.md).

The official character-profile image was used as a visual reference only; the reference file is not distributed in this repository. Reference: [KURO official community profile post](https://www.kurobbs.com/mc/post/1505257912809955328?enter_source=2). [Official game announcement featuring Denia](https://wutheringwaves.kurogames.com/m/en/main/news/detail/4691).

**The fan artwork and underlying character design are excluded from the MIT license.** Wuthering Waves names, characters and designs remain the property of their respective rights holders, including KURO GAMES. Generating a new illustration does not grant rights in the underlying character. No open-content license or official endorsement is asserted for this artwork. The themed distribution therefore contains an open-source application alongside separately governed fan content; it is not an entirely MIT-licensed asset collection. Replace the image and character preset with assets you have suitable rights to if you require an entirely open-licensed distribution.

The Denia character preset is an original fan role-play configuration, not official dialogue. Its original configuration text is covered by the repository license; that license does not grant rights to the underlying character or game setting.

## Removed original images

The three legacy source files (`skeeper.jpg`, `lvklt.png`, and `LANDINGPAGE_Lanscape_4K_noBG.png`) have been omitted from this repository. No separate artwork license was documented for them. No source project history, private runtime files or original image binaries were imported.

## Fonts, icons and dependencies

- Geist (`@fontsource/geist`): SIL Open Font License 1.1; see `third-party-licenses/Geist-OFL.txt`.
- Lucide (`lucide-react`): ISC, with Feather portions retaining their MIT notice; see `third-party-licenses/Lucide-ISC.txt`.
- Application dependencies retain their own licenses. JavaScript and Python packages are installed from the committed lockfiles; their bundled notices remain applicable. The `BAAI/bge-small-zh-v1.5` embedding model is downloaded at runtime and is not bundled here; consult its [model card](https://huggingface.co/BAAI/bge-small-zh-v1.5) for its license.
