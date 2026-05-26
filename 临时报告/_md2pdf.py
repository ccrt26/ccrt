"""将信鸽测试报告 Markdown 转为 PDF（fpdf + CJK 字体）"""
import re, sys
from fpdf import FPDF

FONT_PATH = "C:/Windows/Fonts/simsun.ttc"
TITLE_SIZE = 16; H1_SIZE = 13; H2_SIZE = 11; H3_SIZE = 10; BODY_SIZE = 9
CODE_SIZE = 7; SMALL_SIZE = 7

class MD2PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("CJK", "", FONT_PATH)
        self.add_font("CJK", "B", FONT_PATH)
        self.set_auto_page_break(True, 18)
        self.w = 190; self.margin = 10

    def write_body(self, text, bold=False, size=BODY_SIZE):
        self.set_font("CJK", "B" if bold else "", size)
        self.multi_cell(self.w, size * 0.7, text, align="L")

    def write_code(self, text, size=CODE_SIZE):
        self.set_font("CJK", "", size)
        self.set_fill_color(240, 240, 240)
        self.multi_cell(self.w, size * 0.6, text, align="L", fill=True)

    def write_title(self, text):
        self.set_font("CJK", "B", TITLE_SIZE)
        self.multi_cell(self.w, TITLE_SIZE * 0.8, text, align="C")
        self.ln(4)

    def write_h1(self, text):
        self.ln(3)
        self.set_font("CJK", "B", H1_SIZE)
        self.set_draw_color(26, 24, 46)
        self.set_line_width(0.4)
        y = self.get_y()
        self.multi_cell(self.w, H1_SIZE * 0.7, text, align="L")
        self.line(self.margin, self.get_y() + 1, self.margin + self.w, self.get_y() + 1)
        self.ln(4)

    def write_h2(self, text):
        self.ln(2)
        self.set_font("CJK", "B", H2_SIZE)
        self.multi_cell(self.w, H2_SIZE * 0.7, text, align="L")
        self.ln(1)

    def write_h3(self, text):
        self.ln(1)
        self.set_font("CJK", "B", H3_SIZE)
        self.multi_cell(self.w, H3_SIZE * 0.7, text, align="L")

    def write_hr(self):
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(self.margin, self.get_y(), self.margin + self.w, self.get_y())
        self.ln(2)

    def write_table(self, rows):
        """rows: list of lists of strings"""
        if not rows: return
        ncols = max(len(r) for r in rows)
        col_w = self.w / ncols
        row_h = 6
        header_size = BODY_SIZE - 1
        cell_size = BODY_SIZE - 1

        # header
        self.set_fill_color(26, 24, 46)
        self.set_text_color(255, 255, 255)
        self.set_font("CJK", "B", header_size)
        for i, cell in enumerate(rows[0]):
            x = self.margin + i * col_w
            self.set_xy(x, self.get_y())
            self.cell(col_w, row_h, cell[:50], border=0, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(row_h + 1)

        # body
        for ri, row in enumerate(rows[1:]):
            if ri % 2 == 0:
                self.set_fill_color(245, 245, 250)
            else:
                self.set_fill_color(255, 255, 255)
            self.set_font("CJK", "", cell_size)

            # calculate max height needed
            max_lines = 1
            for cell in row:
                lines = self.multi_cell(col_w - 1, cell_size * 0.55, cell[:80],
                                        dry_run=True, output="LINES")
                max_lines = max(max_lines, len(lines))

            cell_h = max(max_lines * cell_size * 0.55 + 2, row_h)

            # check page break
            if self.get_y() + cell_h > self.h - self.b_margin:
                self.add_page()

            y_before = self.get_y()
            for i, cell in enumerate(row):
                x = self.margin + i * col_w
                self.set_xy(x, y_before)
                self.multi_cell(col_w - 1, cell_size * 0.55, cell[:80],
                                border=0, fill=True)
            self.set_y(y_before + cell_h)

        self.ln(3)

    def write_blockquote(self, text):
        self.set_fill_color(230, 235, 245)
        self.set_text_color(60, 60, 80)
        self.set_font("CJK", "", BODY_SIZE)
        x0 = self.margin + 3
        self.set_x(x0)
        self.multi_cell(self.w - 3, BODY_SIZE * 0.65, text, align="L", fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)


def parse_md(text):
    """Simple md line-by-line parser → list of (type, content) tuples"""
    lines = text.split("\n")
    result = []
    in_code = False
    code_lines = []
    table_rows = []
    in_table = False

    for line in lines:
        # code block
        if line.strip().startswith("```"):
            if in_code:
                result.append(("code", "\n".join(code_lines)))
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        # table
        if "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            # skip separator line
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            table_rows.append(cells)
            continue
        elif table_rows:
            result.append(("table", table_rows))
            table_rows = []
            in_table = False

        # hr
        if re.match(r"^[-*_]{3,}$", line.strip()):
            result.append(("hr", None))
            continue

        # blockquote
        if line.startswith("> "):
            result.append(("blockquote", line[2:]))
            continue

        # headings
        if line.startswith("# "):
            result.append(("title", line[2:]))
        elif line.startswith("## "):
            result.append(("h1", line[3:]))
        elif line.startswith("### "):
            result.append(("h2", line[4:]))
        elif line.startswith("#### "):
            result.append(("h3", line[5:]))
        elif line.strip():
            # inline formatting
            text = line.strip()
            # bold: **text**
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            result.append(("body", text))
        else:
            result.append(("blank", None))

    if table_rows:
        result.append(("table", table_rows))
    return result


def render_to_pdf(md_text, output_path, title_override=None):
    elements = parse_md(md_text)
    pdf = MD2PDF()
    pdf.add_page()

    for etype, content in elements:
        if etype == "title":
            pdf.write_title(content)
        elif etype == "h1":
            pdf.write_h1(content)
        elif etype == "h2":
            pdf.write_h2(content)
        elif etype == "h3":
            pdf.write_h3(content)
        elif etype == "body":
            # handle inline bold
            parts = re.split(r"(<b>.+?</b>)", content)
            for part in parts:
                if part.startswith("<b>") and part.endswith("</b>"):
                    pdf.write_body(part[3:-4], bold=True)
                elif part.strip():
                    pdf.write_body(part.strip())
        elif etype == "code":
            pdf.write_code(content)
        elif etype == "table":
            pdf.write_table(content)
        elif etype == "hr":
            pdf.write_hr()
        elif etype == "blockquote":
            pdf.write_blockquote(content)
        elif etype == "blank":
            pdf.ln(3)

    pdf.output(output_path)
    print(f"PDF generated: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        md_path, out_path = sys.argv[1], sys.argv[2]
    else:
        md_path = "临时报告/信鸽采集测试报告_20260526.md"
        out_path = "临时报告/信鸽采集测试报告_20260526.pdf"

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    render_to_pdf(md_text, out_path)
