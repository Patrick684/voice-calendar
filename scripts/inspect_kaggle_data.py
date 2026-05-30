"""检查 Kaggle 中文时间表达数据集结构"""

import zipfile
import xml.etree.ElementTree as ET

xlsx_path = "C:/downloads/archive/1000_date_and_time_expression_in_Chinese.xlsx"

z = zipfile.ZipFile(xlsx_path)

# 获取共享字符串表
ss = ET.parse(z.open("xl/sharedStrings.xml"))
ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
strings = []
for si in ss.findall(".//s:si", ns):
    # 拼接同一个 si 下的所有 t 文本
    texts = [t.text or "" for t in si.findall(".//s:t", ns)]
    strings.append("".join(texts))

print(f"共享字符串数: {len(strings)}")
print(f"前5个: {strings[:5]}")
print()

# 解析工作表
ws = ET.parse(z.open("xl/worksheets/sheet1.xml"))
rows = ws.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")
print(f"总行数: {len(rows)}")
print()

# 解析每行数据
cell_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def get_cell_value(cell, shared_strings):
    """获取单元格值"""
    t = cell.get("t")  # 类型：s=string, n=number
    v_elem = cell.find(f"{{{cell_ns}}}v")
    if v_elem is None:
        return ""
    v = v_elem.text or ""
    if t == "s":
        return shared_strings[int(v)]
    return v


# 打印前20行
print("=" * 60)
print("前20行数据:")
print("=" * 60)
for i, row in enumerate(rows[:20]):
    cells = row.findall(f"{{{cell_ns}}}c")
    values = [get_cell_value(c, strings) for c in cells]
    print(f"Row {i}: {values}")

# 打印随机几行看更多样本
print()
print("=" * 60)
print("中间样本 (row 100-110):")
print("=" * 60)
for i, row in enumerate(rows[100:110], start=100):
    cells = row.findall(f"{{{cell_ns}}}c")
    values = [get_cell_value(c, strings) for c in cells]
    print(f"Row {i}: {values}")

# 打印尾部
print()
print("=" * 60)
print(f"尾部样本 (row {len(rows) - 5} - {len(rows) - 1}):")
print("=" * 60)
for i, row in enumerate(rows[-5:], start=len(rows) - 5):
    cells = row.findall(f"{{{cell_ns}}}c")
    values = [get_cell_value(c, strings) for c in cells]
    print(f"Row {i}: {values}")
