import os
import re


def create_project_structure(structure_file='structure.txt'):
    """
    從一個文字檔案讀取項目結構並在檔案系統中生成對應的文件和文件夾。

    這個腳本的主要功能是自動化專案的初始化過程，確保所有開發者
    都有一致的起始結構。

    腳本會：
    1. 假設此腳本與結構定義檔 (structure.txt) 位於同一個專案根目錄中。
    2. 逐行解析 structure.txt 中的樹狀結構。
    3. 根據解析出的結構，創建所有指定的文件夾和空的檔案。
    4. 如果文件或文件夾已經存在，腳本會跳過創建步驟，不會覆蓋現有內容。

    Args:
        structure_file (str): 包含專案結構定義的檔案名稱。預設為 'structure.txt'。
    """
    # --- 步驟 0: 前置檢查與設定 ---

    # 檢查結構定義檔是否存在，如果不存在則印出錯誤訊息並終止函式。
    if not os.path.exists(structure_file):
        print(f"錯誤：找不到結構文件 '{structure_file}'。")
        return

    # 取得此腳本檔案的絕對路徑，並從中推斷出專案的根目錄。
    # __file__ 是一個內建變數，代表當前腳本的檔案名稱。
    # os.path.abspath() 將其轉換為絕對路徑。
    # os.path.dirname() 取得該路徑所在的目錄。
    project_root = os.path.dirname(os.path.abspath(__file__))
    print(f"專案根目錄設定為：{project_root}")
    print("-" * 30)

    # `path_stack` 是一個堆疊(stack)，用於追蹤當前處理行的父目錄路徑。
    # 它的運作方式類似於檔案總管的「上一頁」功能。
    # 初始時，我們將專案根目錄推入堆疊，作為所有頂層項目的父目錄。
    path_stack = [project_root]

    # 使用 'with' 陳述式開啟檔案，確保檔案在處理完畢後會自動關閉。
    # 'encoding='utf-8'' 確保可以正確讀取包含中文字元或其他非 ASCII 字元的檔案。
    with open(structure_file, 'r', encoding='utf-8') as f:
        # 逐行讀取檔案內容。
        for line in f:
            # --- 步驟 1: 解析每一行，確定層級和項目名稱 ---

            # 忽略代表專案根目錄的行以及完全空白的行。
            if line.strip() == 'my-flask-app/' or not line.strip():
                continue

            # 分割行以移除行尾的註解（以 '#' 開頭的部分）。
            # .rstrip() 用於移除行尾的空白字元。
            clean_line = line.split('#')[0].rstrip()

            # 使用正則表達式 `r'[\w\.]'` 尋找第一個 "word character" (字母、數字、底線) 或點。
            # 這一步的目的是為了精確地找到項目名稱的起始位置，忽略前面的樹狀結構字元 (如 '├──', '│  ')。
            match = re.search(r'[\w\.]', clean_line)
            if not match:
                # 如果該行沒有任何有效的檔案或目錄名稱，則跳過。
                continue

            # `start_index` 是項目名稱在該行中的起始索引。
            start_index = match.start()
            # `item_name` 是從起始索引到行尾的子字串，即檔案或目錄的名稱。
            item_name = clean_line[start_index:]

            # 根據名稱前的縮排字元數來計算層級。
            # 這裡假設結構檔中的每一層縮排都是由 4 個字元組成的 (例如 '├── ' 或 '    ')。
            # 層級 0 (根目錄下的項目): 縮排為 4 字元 -> (4 // 4) - 1 = 0
            # 層級 1 (子目錄下的項目): 縮排為 8 字元 -> (8 // 4) - 1 = 1
            # 依此類推...
            level = (start_index // 4) - 1

            # --- 步驟 2: 根據層級構建完整路徑 ---

            # 檢查當前行的層級與 `path_stack` 的深度。
            # 如果當前層級比堆疊的深度還淺 (例如，從子目錄回到父目錄)，
            # 則需要從堆疊中彈出路徑，直到堆疊的深度與當前層級匹配。
            while len(path_stack) > level + 1:
                path_stack.pop()

            # 此時，堆疊最上方的元素 (`path_stack[-1]`) 就是當前項目的父目錄路徑。
            parent_path = path_stack[-1]

            # 清理項目名稱，移除目錄名稱結尾的 '/'，以便 `os.path.join` 能正確運作。
            item_name_cleaned = item_name.strip('/')
            # 使用 `os.path.join` 安全地組合父目錄路徑和項目名稱，形成一個完整的絕對路徑。
            # `os.path.join` 會自動處理不同作業系統的路徑分隔符 (例如 Windows 的 `\` 和 Linux/macOS 的 `/`)。
            full_path = os.path.join(parent_path, item_name_cleaned)

            # --- 步驟 3: 創建文件或目錄 ---

            if item_name.endswith('/'):
                # 如果項目名稱以 '/' 結尾，我們將其視為一個目錄。
                if not os.path.exists(full_path):
                    # 如果該路徑不存在，則使用 `os.makedirs` 創建它。
                    # `os.makedirs` 可以遞歸創建所有不存在的父目錄。
                    os.makedirs(full_path)
                    print(f"創建目錄: {full_path}")
                else:
                    # 如果已存在，則印出提示訊息。
                    print(f"目錄已存在: {full_path}")

                # 最重要的一步：將新創建的目錄路徑推入堆疊，
                # 這樣它就成為了後續縮排行 (子項目) 的父目錄。
                path_stack.append(full_path)
            else:
                # 如果項目名稱不以 '/' 結尾，則視為一個文件。

                # 在創建文件之前，先確保其所在的父目錄存在。
                # `exist_ok=True` 參數告訴 `os.makedirs` 如果目錄已存在，不要拋出錯誤。
                parent_dir = os.path.dirname(full_path)
                os.makedirs(parent_dir, exist_ok=True)

                if not os.path.exists(full_path):
                    # 如果文件不存在，則創建一個空文件。
                    # 'w' 模式會創建一個新文件用於寫入。如果文件已存在，它會被清空。
                    # 這裡我們只打開並立即關閉它，效果就是創建了一個空文件。
                    with open(full_path, 'w', encoding='utf-8') as new_file:
                        pass  # 不需要在文件中寫入任何內容。
                    print(f"創建文件:   {full_path}")
                else:
                    # 如果文件已存在，則印出提示訊息。
                    print(f"文件已存在:   {full_path}")

    print("-" * 30)
    print("專案結構生成完畢！")


# 這是一個 Python 的標準慣例。
# `__name__ == '__main__'` 這段程式碼只有在當這個腳本被直接執行時 (例如 `python create_project.py`) 才會運行。
# 如果這個腳本被其他腳本作為模組導入 (import)，則這段程式碼不會被執行。
if __name__ == '__main__':
    create_project_structure()