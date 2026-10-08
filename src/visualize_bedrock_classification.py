"""Reuse saved TF-IDF/UMAP coordinates and Nova Micro predictions by meeting ID."""
import argparse
import re
from pathlib import Path
from collections import Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

CATEGORIES = {'AWS/インフラ': '#298bd4', 'AI/分析': '#14b8a6', 'セキュリティ': '#f59e0b'}

def load_results(directory):
    coordinates = {}
    for line in (directory / 'analysis_result.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'ID=(\d+)\s+.*?Category=(.*?)\s+UMAP=\(([-\d.]+), ([-\d.]+)\) Title=(.*)', line)
        if match:
            key, human, x, y, title = match.groups()
            if int(key) in coordinates:
                raise ValueError('Duplicate coordinate ID')
            coordinates[int(key)] = (human.strip(), float(x), float(y), title)
    predictions = {}
    for line in (directory / 'bedrock_classification_result.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'ID=\s*(\d+) \| Human=(.*?) \| Bedrock=(.*?) \| (OK|NG)', line)
        if match:
            key, human, predicted, status = match.groups()
            key = int(key)
            if key in predictions or predicted not in CATEGORIES or human not in CATEGORIES:
                raise ValueError('Duplicate ID or invalid category')
            if (human == predicted) != (status == 'OK'):
                raise ValueError('Classification status mismatch')
            predictions[key] = (human, predicted)
    if len(coordinates) != 30 or coordinates.keys() != predictions.keys():
        raise ValueError('Expected matching sets of 30 meeting IDs')
    for key in coordinates:
        if coordinates[key][0] != predictions[key][0]:
            raise ValueError('Human labels disagree between logs')
    correct = sum(h == p for h, p in predictions.values())
    if correct != 24:
        raise ValueError('Expected saved evaluation of 24/30')
    return coordinates, predictions, correct

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'output')
    args = parser.parse_args()
    coordinates, predictions, correct = load_results(args.output_dir)
    font_path = Path('C:/Windows/Fonts/meiryo.ttc')
    if not font_path.exists():
        raise FileNotFoundError('Windows Meiryo Japanese font required')
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(font_path)).get_name(), 'axes.unicode_minus': False})
    fig = plt.figure(figsize=(16, 9), dpi=150, facecolor='#0b1426')
    fig.text(.06, .91, '最終結果：議事録カテゴリマップ', fontsize=27, weight='bold', color='white')
    fig.text(.06, .855, '議事録30件 → Amazon Bedrock / Nova Microで3カテゴリへ自動分類', fontsize=14, color='#b8c8df')
    ax = fig.add_axes([.07, .17, .59, .60], facecolor='#111f35')
    for category, color in CATEGORIES.items():
        keys = [k for k in coordinates if predictions[k][1] == category]
        ax.scatter([coordinates[k][1] for k in keys], [coordinates[k][2] for k in keys], s=180, color=color, edgecolors='white', linewidths=.7, zorder=3)
    for key, (_, x, y, _) in coordinates.items():
        ax.annotate(str(key), (x, y), xytext=(7, 6), textcoords='offset points', fontsize=10, color='white', zorder=4)
        if predictions[key][0] != predictions[key][1]:
            ax.scatter([x], [y], s=330, facecolors='none', edgecolors='#fb7185', linewidths=1.8, zorder=3)
    ax.margins(.12)
    ax.set_xlabel('UMAP 1', color='#b8c8df', labelpad=10)
    ax.set_ylabel('UMAP 2', color='#b8c8df', labelpad=10)
    ax.tick_params(colors='#b8c8df')
    ax.grid(alpha=.12, color='white')
    for spine in ax.spines.values():
        spine.set_color('#33445e')
    fig.text(.72, .75, 'マップの読み方', fontsize=20, weight='bold', color='white')
    fig.text(.72, .66, '点1つ = 議事録1件\n位置 = 本文のTF-IDF＋UMAP\n色 = AIの予測カテゴリ\n数字 = 議事録ID', fontsize=13, linespacing=1.9, color='#b8c8df', va='top')
    counts = Counter(p for _, p in predictions.values())
    for index, (category, color) in enumerate(CATEGORIES.items()):
        fig.text(.72, .43 - index * .05, f'●  {category}   {counts[category]}件', fontsize=14, color=color)
    fig.text(.72, .24, f'Accuracy {correct / 30:.1%}', fontsize=23, weight='bold', color='white')
    fig.text(.72, .195, '24 / 30 正解  ・  赤い外枠 = 誤分類6件', fontsize=11, color='#fda4af')
    fig.text(.07, .065, '保存済みTF-IDF＋UMAP座標（小数3桁）を再利用。近い点ほど文章の特徴が似ています。', fontsize=11, color='#b8c8df')
    fig.text(.07, .03, '30件の検証データに対する評価です。UMAPの軸に固有の意味はありません。', fontsize=10, color='#8195b3')
    destination = args.output_dir / 'bedrock_classification_map.png'
    fig.savefig(destination, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'Saved: {destination} (2400 x 1350); matched 30 IDs; accuracy 24/30')

if __name__ == '__main__':
    main()
