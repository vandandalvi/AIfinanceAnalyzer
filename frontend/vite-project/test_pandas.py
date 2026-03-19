import pandas as pd
df = pd.DataFrame({'Date': ['01 Feb, 2026', ''], 'Debit': ['-221.36', ''], 'Credit': ['+250.00', '+5,355.40']})

# Clean commas and signs for pdf
df['Debit'] = df['Debit'].astype(str).str.replace(',', '', regex=False).str.replace('+', '', regex=False).str.replace('-', '', regex=False)
df['Credit'] = df['Credit'].astype(str).str.replace(',', '', regex=False).str.replace('+', '', regex=False).str.replace('-', '', regex=False)
df['Debit'] = pd.to_numeric(df['Debit'], errors='coerce').fillna(0)
df['Credit'] = pd.to_numeric(df['Credit'], errors='coerce').fillna(0)
df['Amount'] = df['Credit'] - df['Debit']

df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
print(df)
print(df.dropna(subset=['Date', 'Amount']))
