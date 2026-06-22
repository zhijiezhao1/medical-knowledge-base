"""
医学知识库 - 文档解析模块
支持 .docx / .rtf / .txt 三种格式
保留原始格式（字体颜色、高亮、字号等）以及表格列宽
"""
import zipfile
import xml.etree.ElementTree as ET
import re
import os

# Word XML 命名空间
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def parse_docx(file_path):
    """
    解析 .docx 文件，保留格式，返回 (html_content, plain_text)
    docx 本质是 zip 压缩包，包含 word/document.xml
    """
    html_parts = []
    plain_parts = []

    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            # 读取主文档 XML
            with z.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()

            # 读取样式定义（用于解析格式）
            styles = {}
            try:
                with z.open('word/styles.xml') as sf:
                    style_tree = ET.parse(sf)
                    style_root = style_tree.getroot()
                    for style in style_root.iter(f'{{{W}}}style'):
                        style_id = style.get(f'{{{W}}}styleId')
                        if style_id:
                            run_prop = style.find(f'{{{W}}}rPr')
                            styles[style_id] = run_prop
            except KeyError:
                pass

            # 获取 body 元素，直接遍历其子元素（按顺序）
            body = root.find(f'{{{W}}}body')
            if body is not None:
                for child in body:
                    tag = child.tag
                    # 处理表格
                    if tag == f'{{{W}}}tbl':
                        html_table = _parse_table(child, [])
                        if html_table:
                            html_parts.append(html_table)
                    # 处理段落（不在表格内的段落）
                    elif tag == f'{{{W}}}p':
                        html_para, plain_para = _parse_paragraph(child, styles)
                        if html_para:
                            html_parts.append(html_para)
                        if plain_para:
                            plain_parts.append(plain_para)

    except zipfile.BadZipFile:
        raise ValueError("无效的 .docx 文件（文件损坏或不是有效的 Word 文档）")

    html_content = '\n'.join(html_parts)
    plain_text = '\n'.join(plain_parts)
    return html_content, plain_text


def _get_tc_width(tc):
    """提取单元格的宽度（twips）和 gridSpan"""
    tcPr = tc.find(f'{{{W}}}tcPr')
    if tcPr is None:
        return 0, 1

    # gridSpan（跨列数）
    gs = tcPr.find(f'{{{W}}}gridSpan')
    span = int(gs.get(f'{{{W}}}val', 1)) if gs is not None else 1

    # tcW（宽度）
    tcW = tcPr.find(f'{{{W}}}tcW')
    w = 0
    if tcW is not None:
        w_val = tcW.get(f'{{{W}}}w')
        w_type = tcW.get(f'{{{W}}}type', 'dxa')
        if w_val:
            try:
                w = int(w_val)
            except ValueError:
                w = 0

    return w, span


def _get_tc_shading(tc):
    """提取单元格的底色（shading）"""
    tcPr = tc.find(f'{{{W}}}tcPr')
    if tcPr is None:
        return None
    
    shd = tcPr.find(f'{{{W}}}shd')
    if shd is not None:
        fill = shd.get(f'{{{W}}}fill')
        if fill and fill not in ('auto', 'transparent', 'FFFFFFFF', '00FFFFFF'):
            return f'#{fill}'
    return None


def _get_run_style(run_elem):
    """提取 run 元素的样式信息"""
    styles = []

    rPr = run_elem.find(f'{{{W}}}rPr')
    if rPr is None:
        return styles

    # 字体加粗
    if rPr.find(f'{{{W}}}b') is not None or rPr.find(f'{{{W}}}bCs') is not None:
        styles.append('font-weight:bold')

    # 字体斜体
    if rPr.find(f'{{{W}}}i') is not None or rPr.find(f'{{{W}}}iCs') is not None:
        styles.append('font-style:italic')

    # 下划线
    u_elem = rPr.find(f'{{{W}}}u')
    if u_elem is not None:
        styles.append('text-decoration:underline')

    # 删除线
    if rPr.find(f'{{{W}}}strike') is not None:
        styles.append('text-decoration:line-through')

    # 字体颜色
    color_elem = rPr.find(f'{{{W}}}color')
    if color_elem is not None:
        color_val = color_elem.get(f'{{{W}}}val')
        if color_val and color_val not in ('auto', '000000'):
            styles.append(f'color:#{color_val}')

    # 字体高亮（背景色）
    shd_elem = rPr.find(f'{{{W}}}shd')
    if shd_elem is not None:
        fill = shd_elem.get(f'{{{W}}}fill')
        if fill and fill not in ('auto', 'transparent'):
            styles.append(f'background:#{fill}')

    # 字体荧光笔高亮（highlight）
    highlight_elem = rPr.find(f'{{{W}}}highlight')
    if highlight_elem is not None:
        val = highlight_elem.get(f'{{{W}}}val')
        if val and val not in ('none', 'auto', 'clear'):
            # 将Word颜色名转换为十六进制
            color_map = {
                'yellow': '#FFFF00',
                'green': '#00FF00',
                'cyan': '#00FFFF',
                'magenta': '#FF00FF',
                'blue': '#0000FF',
                'red': '#FF0000',
                'darkyellow': '#808000',
                'darkgreen': '#008000',
                'darkcyan': '#008080',
                'darkmagenta': '#800080',
                'darkblue': '#000080',
                'darkred': '#800000',
                'black': '#000000',
                'white': '#FFFFFF',
                'darkgray': '#808080',
                'lightgray': '#C0C0C0',
            }
            hex_color = color_map.get(val.lower(), f'#{val}' if len(val) == 6 else '#FFFF00')
            styles.append(f'background-color:{hex_color}')

    # 字体大小
    sz_elem = rPr.find(f'{{{W}}}sz')
    szCs_elem = rPr.find(f'{{{W}}}szCs')
    sz = sz_elem or szCs_elem
    if sz is not None:
        half_pts = int(sz.get(f'{{{W}}}val', 22))
        px = int(half_pts / 2 * 96 / 72)  # 半点 → 像素（96dpi）
        styles.append(f'font-size:{px}px')

    # 字体名称
    rFonts = rPr.find(f'{{{W}}}rFonts')
    if rFonts is not None:
        eastAsia = rFonts.get(f'{{{W}}}eastAsia')
        ascii_ = rFonts.get(f'{{{W}}}ascii')
        font = eastAsia or ascii_
        if font:
            styles.append(f'font-family:"{font}", sans-serif')

    return styles


def _parse_paragraph(para_elem, styles_dict):
    """解析单个段落，返回 (html_str, plain_str)"""
    runs_html = []
    plain_line = []

    for run in para_elem.iter(f'{{{W}}}r'):
        text_elem = run.find(f'{{{W}}}t')
        if text_elem is None or text_elem.text is None:
            continue

        text = text_elem.text
        inline_styles = _get_run_style(run)

        style_attr = ''
        if inline_styles:
            style_attr = ' style="' + '; '.join(inline_styles) + '"'

        runs_html.append(f'<span{style_attr}>{_escape_html(text)}</span>')
        plain_line.append(text)

    if runs_html:
        # 检测段落样式（标题、加粗居中等）
        pPr = para_elem.find(f'{{{W}}}pPr')
        para_style = ''
        if pPr is not None:
            pStyle = pPr.find(f'{{{W}}}pStyle')
            if pStyle is not None:
                style_id = pStyle.get(f'{{{W}}}val', '')
                # 识别标题样式
                if 'heading' in style_id.lower() or style_id.lower() in ('1', '2', '3', '4', '5', '6'):
                    level = style_id[-1] if style_id[-1].isdigit() else '1'
                    para_style = f' font-size:{18-int(level)*1.5}px; font-weight:bold'

        p_style_attr = f' style="{para_style}"' if para_style else ''
        html_para = f'<p{p_style_attr}>{"".join(runs_html)}</p>'
        return html_para, ''.join(plain_line)

    return None, None


def _parse_table(table_elem, col_pcts):
    """
    解析 Word 表格
    col_pcts: 每列宽度的百分比列表
    """
    rows_out = []

    for ri, tr in enumerate(table_elem.iter(f'{{{W}}}tr')):
        cells_out = []
        col_idx = 0

        for tc in tr.iter(f'{{{W}}}tc'):
            tcPr = tc.find(f'{{{W}}}tcPr')

            # 垂直合并（vMerge）
            vmerge = None
            if tcPr is not None:
                vm = tcPr.find(f'{{{W}}}vMerge')
                if vm is not None:
                    vmerge = vm.get(f'{{{W}}}val')

            # gridSpan（跨列）
            gs = tcPr.find(f'{{{W}}}gridSpan') if tcPr is not None else None
            colspan = int(gs.get(f'{{{W}}}val', 1)) if gs is not None else 1

            # continue 合并格：跳过，不输出
            if vmerge == 'continue':
                col_idx += colspan
                continue

            # 获取单元格底色
            bg_color = _get_tc_shading(tc)
            
            # 构建单元格样式
            cell_styles = []
            
            # 底色
            if bg_color:
                cell_styles.append(f'background-color:{bg_color}')
            
            # 跨列时，用 colspan_pct；单列时用 width_pct
            if colspan > 1:
                colspan_pct = sum(col_pcts[col_idx:col_idx + colspan]) if col_idx < len(col_pcts) else 0
                width_attr = f' width="{colspan_pct:.1f}%"' if colspan_pct > 0 else ''
            else:
                width_pct = col_pcts[col_idx] if col_idx < len(col_pcts) else 0
                width_attr = f' width="{width_pct:.1f}%"' if width_pct > 0 else ''

            # 解析单元格内容
            cell_content = []
            for para in tc.iter(f'{{{W}}}p'):
                html_p, plain_p = _parse_paragraph(para, {})
                if html_p:
                    cell_content.append(html_p)

            tag = 'th' if ri == 0 else 'td'
            content_str = ''.join(cell_content)
            colspan_attr = f' colspan="{colspan}"' if colspan > 1 else ''
            
            # 组装样式属性
            style_attr = ''
            if cell_styles:
                style_attr = ' style="' + '; '.join(cell_styles) + '"'
            
            cell_html = f'<{tag}{width_attr}{colspan_attr}{style_attr}>{content_str}</{tag}>'
            cells_out.append(cell_html)

            col_idx += colspan

        rows_out.append('<tr>' + ''.join(cells_out) + '</tr>')

    if rows_out:
        return (
            '<table style="border-collapse:collapse;width:100%;border:1px solid #000;margin:8px 0;table-layout:fixed">'
            + ''.join(rows_out)
            + '</table>'
        )
    return None


def parse_txt(file_path):
    """解析纯文本文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030']
    html_content = None
    plain_text = None

    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
            plain_text = content
            # 文本文件每行用 <p> 包裹
            lines = content.split('\n')
            html_parts = [f'<p>{_escape_html(line)}</p>' for line in lines if line.strip()]
            html_content = '\n'.join(html_parts)
            break
        except UnicodeDecodeError:
            continue

    if html_content is None:
        raise ValueError("无法解码文本文件，请确认文件编码为 UTF-8 或 GBK")

    return html_content, plain_text


def parse_rtf(file_path):
    """
    解析 RTF 文件（简化实现）
    提取纯文本，保留加粗/斜体/颜色信息
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()

        # 尝试解码
        for enc in ['utf-8', 'gbk', 'latin-1']:
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        # RTF 简化解析：提取纯文本，保留基本格式
        result_parts = []
        i = 0
        bold_depth = 0
        italic_depth = 0
        current_text = []

        while i < len(text):
            c = text[i]

            if c == '{':
                if i + 1 < len(text) and text[i+1] == '\\':
                    j = i + 2
                    while j < len(text) and text[j].isalpha():
                        j += 1
                    ctrl_word = text[i+2:j] if j > i+2 else text[i+1:j]
                    ctrl_char = text[j] if j < len(text) else ''

                    if ctrl_word in ('b', 'bold'):
                        bold_depth += 1
                        current_text.append('<strong>')
                    elif ctrl_word in ('i', 'italic'):
                        italic_depth += 1
                        current_text.append('<em>')
                    elif ctrl_word in ('ul', 'ulnone'):
                        current_text.append('</u>' if ctrl_word == 'ul' else '')
                    elif ctrl_word in ('cf', 'color'):
                        k = j
                        while k < len(text) and text[k].isdigit():
                            k += 1
                        if k > j:
                            color_val = text[j:k]
                            if len(color_val) <= 8:
                                current_text.append(f'<span style="color:#{color_val}">')
                    elif ctrl_word in ('highlight'):
                        k = j
                        while k < len(text) and (text[k].isdigit() or text[k] == '-'):
                            k += 1
                        if k > j:
                            hl_val = text[j:k]
                            current_text.append(f'<span style="background:#{hl_val}">')
                    elif ctrl_word == '':
                        pass

                    i = j
                    if ctrl_char and ctrl_char not in ' {':
                        i += 1
                    continue

                i += 1
                continue

            elif c == '}':
                if bold_depth > 0:
                    current_text.append('</strong>')
                    bold_depth -= 1
                if italic_depth > 0:
                    current_text.append('</em>')
                    italic_depth -= 1
                if current_text and current_text[-1].startswith('<span'):
                    current_text.append('</span>')
                i += 1
                continue

            elif c == '\\':
                if i + 1 < len(text):
                    next_c = text[i+1]
                    if next_c == "'":
                        hex_val = text[i+2:i+4] if i+4 <= len(text) else ''
                        try:
                            char = bytes.fromhex(hex_val).decode('latin-1', errors='replace')
                            current_text.append(char)
                        except ValueError:
                            pass
                        i += 4
                        continue
                    elif next_c in ('n', 'par', 'line'):
                        current_text.append('\n')
                        i += 2
                        if next_c == 'par':
                            i += 1
                        continue
                    elif next_c == '{' or next_c == '}' or next_c == '\\':
                        current_text.append(next_c)
                        i += 2
                        continue
                    elif next_c.isalpha():
                        j = i + 2
                        while j < len(text) and text[j].isalpha():
                            j += 1
                        while j < len(text) and (text[j].isdigit() or text[j] == '-'):
                            j += 1
                        if j < len(text) and text[j] == ' ':
                            j += 1
                        i = j
                        continue
                    elif next_c == ' ':
                        current_text.append(' ')
                        i += 2
                        continue
                i += 1
                continue

            elif c == '\r' or c == '\n':
                if current_text and current_text[-1] != '\n':
                    current_text.append('\n')
                i += 1
                continue

            else:
                current_text.append(c)
                i += 1

        raw_text = ''.join(current_text)
        plain_text = re.sub(r'\n{3,}', '\n\n', raw_text)

        lines = plain_text.split('\n')
        html_parts = [f'<p>{_escape_html(line)}</p>' for line in lines if line.strip()]
        html_content = '\n'.join(html_parts) if html_parts else f'<p>{_escape_html(plain_text)}</p>'

        return html_content, plain_text

    except Exception as e:
        raise ValueError(f"RTF 解析失败: {str(e)}")


def parse_file(file_path):
    """
    统一入口：根据文件扩展名选择解析器
    返回 (html_content, plain_text, format)
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.docx':
        return parse_docx(file_path) + ('docx',)
    elif ext == '.txt':
        return parse_txt(file_path) + ('txt',)
    elif ext == '.rtf':
        return parse_rtf(file_path) + ('rtf',)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .docx / .rtf / .txt")


def _escape_html(text):
    """HTML 实体转义"""
    if not text:
        return ''
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        html, plain, fmt = parse_file(sys.argv[1])
        print(f"格式: {fmt}")
        print(f"纯文本长度: {len(plain)}")
        print(f"HTML 预览: {html[:200]}")
