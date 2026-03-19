import pdfplumber
import sys

def parse_pdf(path):
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"--- PAGE {i} ---")
            tables = page.extract_tables()
            for t_idx, table in enumerate(tables):
                print(f"Table {t_idx}:")
                for row_idx, row in enumerate(table[:5]): # print first 5 rows
                    print(row)

if __name__ == "__main__":
    parse_pdf(sys.argv[1])
