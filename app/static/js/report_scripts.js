document.addEventListener('DOMContentLoaded', function() {
    const reportTableContainer = document.querySelector('.table-responsive');
    if (!reportTableContainer) return;

    const editBtn = document.querySelector('.edit-button');
    const saveBtn = document.querySelector('.save-button');
    const cancelBtn = document.querySelector('.cancel-button');
    const reportType = reportTableContainer.dataset.reportType;

    // 將所有數字格式化為不帶逗號的字串，以便進行計算
    function getCleanNumber(str) {
        if (typeof str !== 'string') return str || 0;
        return parseFloat(str.replace(/[^0-9.-]/g, '')) || 0;
    }

    function formatAsCurrency(number) {
        return `$${new Intl.NumberFormat('en-US').format(Math.round(number))}`;
    }

    function formatAsNumber(number) {
        return Math.round(number).toLocaleString('en-US');
    }
    
    function getNumericValue(element) {
        if (!element) return 0;
        const text = element.innerText.replace(/[^0-9.-]/g, '');
        return parseFloat(text) || 0;
    }

    // 更新 daily_summary 的計算欄位
    function updateDailySummaryRow(row) {
        const openingCash = getCleanNumber(row.querySelector('[data-field="opening_cash"] .editable-input').value);
        const totalSales = getNumericValue(row.querySelector('[data-field="total_sales"]'));
        const closingCash = getNumericValue(row.querySelector('[data-field="closing_cash"]'));

        const expectedCash = openingCash + totalSales;
        const cashDiff = closingCash - expectedCash;

        row.querySelector('[data-field="expected_cash"]').innerText = formatAsCurrency(expectedCash);
        row.querySelector('[data-field="cash_diff"]').innerText = formatAsCurrency(cashDiff);
        
        // 更新帳差顏色
        const cashDiffCell = row.querySelector('[data-field="cash_diff"]');
        cashDiffCell.classList.toggle('text-danger', cashDiff < 0);
    }
    
    // 更新 daily_cash_summary 的計算欄位
    function updateDailyCashSummaryRow(row) {
        const donationTotal = getCleanNumber(row.querySelector('[data-field="donation_total"] .editable-input').value);
        const otherTotal = getCleanNumber(row.querySelector('[data-field="other_total"] .editable-input').value);
        const otherCashCell = row.querySelector('[data-field="other_cash"]');
        
        const totalOtherCash = donationTotal + otherTotal;
        otherCashCell.innerText = `NT$ ${formatAsNumber(totalOtherCash)}`;
    }
    
    // 更新 transaction_log 的計算欄位
    function updateTransactionLogRow(row) {
        const itemPriceInputs = row.querySelectorAll('[data-item-id] .editable-input');
        const transactionAmountCell = row.querySelector('[data-field="amount"]');
        const cashReceivedInput = row.querySelector('[data-field="cash_received"] .editable-input');
        const changeGivenCell = row.querySelector('[data-field="change_given"]');

        let newTransactionAmount = 0;
        itemPriceInputs.forEach(input => {
            newTransactionAmount += getCleanNumber(input.value);
        });

        transactionAmountCell.innerText = formatAsCurrency(newTransactionAmount);
        
        const cashReceived = getCleanNumber(cashReceivedInput.value);
        const changeGiven = cashReceived - newTransactionAmount;
        changeGivenCell.innerText = formatAsCurrency(changeGiven);
    }

    // 更新 daily_cash_check 的計算欄位
    function updateDailyCashCheckRow(row) {
        let closingCash = 0;
        row.querySelectorAll('.cash-breakdown-input').forEach(input => {
            const denom = getCleanNumber(input.dataset.denom);
            const count = getCleanNumber(input.value);
            closingCash += denom * count;
        });
        const closingCashDisplay = row.querySelector('.closing_cash_display');
        if (closingCashDisplay) {
            closingCashDisplay.innerText = `NT$ ${formatAsNumber(closingCash)}`;
        }
        
        // 更新總計行
        const grandTotalRow = document.querySelector('.fw-bold.table-secondary');
        if (grandTotalRow) {
            let grandClosingCash = 0;
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(dataRow => {
                const dataRowClosingCash = getCleanNumber(dataRow.querySelector('.closing_cash_display').innerText);
                grandClosingCash += dataRowClosingCash;
            });
            grandTotalRow.querySelector('.grand-total-closing-cash').innerText = `NT$ ${formatAsNumber(grandClosingCash)}`;
            
            reportTableContainer.querySelectorAll('.cash-breakdown-input').forEach(input => {
                const denom = input.dataset.denom;
                let denomTotal = 0;
                reportTableContainer.querySelectorAll(`tr[data-id] .cash-breakdown-input[data-denom="${denom}"]`).forEach(denomInput => {
                    denomTotal += getCleanNumber(denomInput.value);
                });
                const totalCell = grandTotalRow.querySelector(`[data-denom-total="${denom}"]`);
                if (totalCell) {
                    totalCell.innerText = formatAsNumber(denomTotal);
                }
            });
        }
    }

    function toggleEditMode(isEditing) {
        reportTableContainer.classList.toggle('editing', isEditing);
        if (isEditing) {
            editBtn.style.display = 'none';
            saveBtn.style.display = 'inline-block';
            cancelBtn.style.display = 'inline-block';
        } else {
            editBtn.style.display = 'inline-block';
            saveBtn.style.display = 'none';
            cancelBtn.style.display = 'none';
        }
    }

    // 點擊「編輯」按鈕
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            const originalData = {};
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                const rowId = row.dataset.id;
                originalData[rowId] = {};
                row.querySelectorAll('.editable-cell').forEach(cell => {
                    const field = cell.dataset.field;
                    const displayValueElement = cell.querySelector('.display-value');
                    const inputValueElement = cell.querySelector('.editable-input');
                    const rawValue = getCleanNumber(displayValueElement.innerText);
                    
                    if (field) {
                        if (cell.classList.contains('cash-breakdown-cell')) {
                            const denom = inputValueElement.dataset.denom;
                            if (!originalData[rowId].cash_breakdown) originalData[rowId].cash_breakdown = {};
                            originalData[rowId].cash_breakdown[denom] = rawValue;
                        } else {
                            originalData[rowId][field] = rawValue;
                        }
                        inputValueElement.value = rawValue;
                    } else if (cell.dataset.itemId) { // For transaction_log
                         const itemId = cell.dataset.itemId;
                         if (!originalData[rowId].items) originalData[rowId].items = {};
                         originalData[rowId].items[itemId] = rawValue;
                         inputValueElement.value = rawValue;
                    }
                });
            });
            reportTableContainer.dataset.originalData = JSON.stringify(originalData);

            toggleEditMode(true);
        });
    }

    // 點擊「放棄」按鈕
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            const originalData = JSON.parse(reportTableContainer.dataset.originalData);
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                const rowId = row.dataset.id;
                if (originalData[rowId]) {
                    row.querySelectorAll('.editable-cell').forEach(cell => {
                        const field = cell.dataset.field;
                        const displayValueElement = cell.querySelector('.display-value');
                        const inputValueElement = cell.querySelector('.editable-input');
                        
                        if (field && originalData[rowId][field] !== undefined) {
                            displayValueElement.innerText = formatAsCurrency(originalData[rowId][field]);
                            inputValueElement.value = originalData[rowId][field];
                        } else if (cell.classList.contains('cash-breakdown-cell') && originalData[rowId].cash_breakdown) {
                            const denom = inputValueElement.dataset.denom;
                            if (originalData[rowId].cash_breakdown[denom] !== undefined) {
                                displayValueElement.innerText = originalData[rowId].cash_breakdown[denom];
                                inputValueElement.value = originalData[rowId].cash_breakdown[denom];
                            }
                        } else if (cell.dataset.itemId && originalData[rowId].items) {
                            const itemId = cell.dataset.itemId;
                            if (originalData[rowId].items[itemId] !== undefined) {
                                displayValueElement.innerText = formatAsCurrency(originalData[rowId].items[itemId]);
                                inputValueElement.value = originalData[rowId].items[itemId];
                            }
                        }
                    });
                }
            });
            
            // 重新計算所有依賴欄位
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                if (reportType === 'daily_summary') updateDailySummaryRow(row);
                if (reportType === 'daily_cash_summary') updateDailyCashSummaryRow(row);
                if (reportType === 'transaction_log') updateTransactionLogRow(row);
                if (reportType === 'daily_cash_check') updateDailyCashCheckRow(row);
            });
            
            toggleEditMode(false);
        });
    }
    
    // 處理表單提交
    const editableForm = document.getElementById(`editable-form-${reportType}`);
    if (editableForm) {
        editableForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const updatedData = [];
            let isValid = true;

            reportTableContainer.querySelectorAll('tbody tr[data-id]').forEach(row => {
                const rowId = row.dataset.id;
                const rowData = { id: rowId };

                // 處理單一欄位
                row.querySelectorAll('.editable-cell').forEach(cell => {
                    const field = cell.dataset.field;
                    const input = cell.querySelector('.editable-input');
                    if (input) {
                        const value = getCleanNumber(input.value);
                        if (field) {
                            if (input.dataset.denom) { // 處理現金盤點
                                if (!rowData.cash_breakdown) rowData.cash_breakdown = {};
                                rowData.cash_breakdown[input.dataset.denom] = value;
                            } else {
                                rowData[field] = value;
                            }
                        }
                    }
                });

                // 處理多個項目 (特別針對 transaction_log)
                if (reportType === 'transaction_log') {
                    rowData.items = [];
                    row.querySelectorAll('[data-item-id]').forEach(itemCell => {
                        const itemId = itemCell.dataset.itemId;
                        const input = itemCell.querySelector('.editable-input');
                        if (input) {
                            rowData.items.push({
                                id: itemId,
                                price: getCleanNumber(input.value)
                            });
                        }
                    });
                }
                
                updatedData.push(rowData);
            });
            
            if (!isValid) {
                alert('請檢查輸入的數據。');
                return;
            }

            try {
                const response = await fetch(editableForm.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name="csrf_token"]').value
                    },
                    body: JSON.stringify(updatedData)
                });

                const result = await response.json();
                if (result.success) {
                    window.location.reload();
                } else {
                    alert('儲存失敗：' + result.message);
                }
            } catch (error) {
                console.error('Error:', error);
                alert('儲存時發生網路錯誤，請稍後再試。');
            }
        });
    }

    // 實時更新計算欄位
    reportTableContainer.addEventListener('input', function(event) {
        const input = event.target;
        if (input.classList.contains('editable-input')) {
            const row = input.closest('tr');
            if (reportType === 'daily_summary') updateDailySummaryRow(row);
            if (reportType === 'daily_cash_summary') updateDailyCashSummaryRow(row);
            if (reportType === 'transaction_log') updateTransactionLogRow(row);
            if (reportType === 'daily_cash_check') updateDailyCashCheckRow(row);
        }
    });

    // 初始設置
    toggleEditMode(false);
});