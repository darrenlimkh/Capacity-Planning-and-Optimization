import pandas as pd

def write_to_excel_with_formatting(data, filename):
    """ reformats excel file to autofit column width, bold texts, warp texts, align texts, set text & background colour
    :param data: compilation of all required dataframes. 
    :type data: dict
    :param filename: output filename
    :type filename: str
    """
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    for sheet_name, df in data.items():
        df.to_excel(writer, sheet_name=sheet_name, startrow=1, header=False, index=False)

        workbook  = writer.book
        worksheet = writer.sheets[sheet_name]

        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
            'fg_color': '347da2',
            'font_color': 'white',
            'font_size': 12,
        })

        worksheet.set_row(0, 30.8) 
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            column_len = df[value].astype(str).str.len().max()
            column_len = max(column_len, len(value)) + 3
            worksheet.set_column(col_num, col_num, column_len)
    writer.save()