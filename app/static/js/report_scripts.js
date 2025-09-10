document.addEventListener('DOMContentLoaded', function() {
    const reportTableContainer = document.querySelector('.table-responsive');
    if (!reportTableContainer) return;

    const editBtn = document.querySelector('.edit-button');
    const saveBtn = document.querySelector('.save-button');
    const cancelBtn = document.querySelector('.cancel-button');
    const reportType = reportTableContainer.dataset.reportType;
    
    // 獲取所有類別資料，用於交易細節編輯
    const all_categories_json = document.querySelector('script[type="application/json"]#all-categories-data');
    const all_categories = all_categories_json ? JSON.parse(all_categories_json.textContent) : [];
    
    // 預先建立一個類別 ID 到類型名稱的映射，方便快速查詢
    const categoryTypeMap = all_categories.reduce((map, c) => {
        map[c.id] = c.category_type;
        return map;
    }, {});
    
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

    function updateDailySummaryRow(row) {
        const openingCash = getCleanNumber(row.querySelector('[data-field="opening_cash"] .editable-input').value);
        const totalSales = getNumericValue(row.querySelector('[data-field="total_sales"]'));
        const closingCash = getNumericValue(row.querySelector('[data-field="closing_cash"]'));
        const expectedCash = openingCash + totalSales;
        const cashDiff = closingCash - expectedCash;
        row.querySelector('[data-field="expected_cash"]').innerText = formatAsCurrency(expectedCash);
        row.querySelector('[data-field="cash_diff"]').innerText = formatAsCurrency(cashDiff);
        const cashDiffCell = row.querySelector('[data-field="cash_diff"]');
        cashDiffCell.classList.toggle('text-danger', cashDiff < 0);
    }
    
    function updateDailyCashSummaryRow(row) {
        // 這兩個欄位現在是唯讀，所以無需更新
    }
    
    function updateTransactionLogRow(row) {
        const transactionRows = reportTableContainer.querySelectorAll(`tr[data-id="${row.dataset.id}"]`);
        let newTransactionAmount = 0;
        transactionRows.forEach(transRow => {
            const itemPriceInput = transRow.querySelector('[data-item-id] .editable-input');
            if (itemPriceInput) {
                newTransactionAmount += getCleanNumber(itemPriceInput.value);
            }
        });
        const transactionAmountCell = row.querySelector('[data-field="amount"]');
        if (transactionAmountCell) {
            transactionAmountCell.innerText = formatAsCurrency(newTransactionAmount);
        }
        const firstRowOfTransaction = transactionRows[0];
        const cashReceivedInput = firstRowOfTransaction.querySelector('[data-field="cash_received"] .editable-input');
        const changeGivenCell = firstRowOfTransaction.querySelector('[data-field="change_given"]');
        const cashReceived = getCleanNumber(cashReceivedInput.value);
        const changeGiven = cashReceived - newTransactionAmount;
        if (changeGivenCell) {
             changeGivenCell.innerText = formatAsCurrency(changeGiven);
        }
    }

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
        const grandTotalRow = document.querySelector('.fw-bold.table-secondary');
        if (grandTotalRow) {
            let grandClosingCash = 0;
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(dataRow => {
                const dataRowClosingCash = getCleanNumber(dataRow.querySelector('.closing_cash_display').innerText);
                grandClosingCash += dataRowClosingCash;
            });
            // 修正：更新總計欄位
            const grandTotalClosingCashCell = grandTotalRow.querySelector('td.closing_cash_display');
            if (grandTotalClosingCashCell) {
                grandTotalClosingCashCell.innerText = `NT$ ${formatAsNumber(grandClosingCash)}`;
            }
            
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
        const isEditableReport = (reportType === 'daily_summary' || reportType === 'daily_cash_check' || reportType === 'transaction_log');
        editBtn.style.display = isEditableReport && !isEditing ? 'inline-block' : 'none';
        saveBtn.style.display = isEditing ? 'inline-block' : 'none';
        cancelBtn.style.display = isEditing ? 'inline-block' : 'none';
        
        if (reportTableContainer) {
            reportTableContainer.classList.toggle('editing', isEditing);
        }
    }

    if (editBtn) {
        editBtn.addEventListener('click', () => {
            const originalData = {};
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                const rowId = row.dataset.id;
                
                if (!originalData[rowId]) {
                    originalData[rowId] = { id: rowId, items: [] };
                }

                if (reportType === 'transaction_log') {
                    const cashReceivedElement = row.querySelector('[data-field="cash_received"] .display-value');
                    const changeGivenElement = row.querySelector('[data-field="change_given"] .display-value');
                    if (cashReceivedElement) {
                        originalData[rowId].cash_received = getCleanNumber(cashReceivedElement.innerText);
                    }
                    if (changeGivenElement) {
                        originalData[rowId].change_given = getCleanNumber(changeGivenElement.innerText);
                    }
                    
                    const itemPriceCell = row.querySelector('[data-field="item_price"]');
                    const categoryCell = row.querySelector('[data-field="category"]');
                    if (itemPriceCell && categoryCell) {
                        const itemId = itemPriceCell.dataset.itemId;
                        const categoryId = categoryCell.dataset.categoryId;
                        originalData[rowId].items.push({
                            id: itemId,
                            price: getCleanNumber(itemPriceCell.querySelector('.display-value').innerText),
                            category_id: categoryId
                        });
                    }
                } else if (reportType === 'daily_summary') {
                    const openingCashCell = row.querySelector('[data-field="opening_cash"]');
                    if (openingCashCell) {
                        originalData[rowId].opening_cash = getCleanNumber(openingCashCell.querySelector('.display-value').innerText);
                    }
                } else if (reportType === 'daily_cash_check') {
                    if (!originalData[rowId].cash_breakdown) {
                        originalData[rowId].cash_breakdown = {};
                    }
                    row.querySelectorAll('.cash-breakdown-input').forEach(input => {
                        const denom = input.dataset.denom;
                        originalData[rowId].cash_breakdown[denom] = getCleanNumber(input.value);
                    });
                }
            });

            reportTableContainer.dataset.originalData = JSON.stringify(originalData);

            reportTableContainer.querySelectorAll('.editable-cell').forEach(cell => {
                const displayValueElement = cell.querySelector('.display-value');
                const editableElement = cell.querySelector('.editable-input, .editable-select');
                if(editableElement && displayValueElement) {
                    if(editableElement.tagName === 'SELECT') {
                        editableElement.value = cell.dataset.categoryId;
                    } else {
                        let rawValue = displayValueElement.innerText.replace('NT$','').replace('$','');
                        editableElement.value = getCleanNumber(rawValue);
                    }
                }
            });
            toggleEditMode(true);
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            const originalData = JSON.parse(reportTableContainer.dataset.originalData);
            
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                const rowId = row.dataset.id;
                const originalTransactionData = originalData[rowId];
                if (!originalTransactionData) return;

                if (reportType === 'transaction_log') {
                    const cashReceivedCell = row.querySelector('[data-field="cash_received"]');
                    const changeGivenCell = row.querySelector('[data-field="change_given"]');
                    
                    if (cashReceivedCell) {
                        const input = cashReceivedCell.querySelector('.editable-input');
                        const span = cashReceivedCell.querySelector('.display-value');
                        input.value = originalTransactionData.cash_received;
                        span.innerText = formatAsCurrency(originalTransactionData.cash_received);
                    }
                    if (changeGivenCell) {
                         changeGivenCell.innerText = formatAsCurrency(originalTransactionData.change_given);
                    }

                    const itemPriceCell = row.querySelector('[data-item-id]');
                    const categoryCell = row.querySelector('[data-field="category"]');
                    if (itemPriceCell && categoryCell) {
                        const itemId = itemPriceCell.dataset.itemId;
                        const originalItemData = originalTransactionData.items.find(item => item.id == itemId);
                        if (originalItemData) {
                            const priceInput = itemPriceCell.querySelector('.editable-input');
                            const priceSpan = itemPriceCell.querySelector('.display-value');
                            priceInput.value = originalItemData.price;
                            priceSpan.innerText = formatAsCurrency(originalItemData.price);

                            const categorySelect = categoryCell.querySelector('.editable-select');
                            const categorySpan = categoryCell.querySelector('.display-value');
                            categorySelect.value = originalItemData.category_id;
                            const categoryName = all_categories.find(c => c.id == originalItemData.category_id)?.name || '手動輸入';
                            categorySpan.innerText = categoryName;
                            categoryCell.dataset.categoryId = originalItemData.category_id;

                            const itemTypeCell = categoryCell.closest('tr').querySelector('td:nth-child(4) .badge');
                            const itemType = categoryTypeMap[originalItemData.category_id];
                            if (itemTypeCell && itemType) {
                                if (itemType.includes('discount')) {
                                    itemTypeCell.classList.remove('bg-success');
                                    itemTypeCell.classList.add('bg-danger');
                                    itemTypeCell.innerText = '折扣';
                                } else {
                                    itemTypeCell.classList.remove('bg-danger');
                                    itemTypeCell.classList.add('bg-success');
                                    itemTypeCell.innerText = '商品';
                                }
                            }
                        }
                    }
                } else if (reportType === 'daily_summary') {
                    const openingCashCell = row.querySelector('[data-field="opening_cash"]');
                    if (openingCashCell) {
                        const input = openingCashCell.querySelector('.editable-input');
                        const span = openingCashCell.querySelector('.display-value');
                        const originalValue = originalTransactionData.opening_cash;
                        input.value = originalValue;
                        span.innerText = formatAsCurrency(originalValue);
                    }
                } else if (reportType === 'daily_cash_check') {
                    row.querySelectorAll('.cash-breakdown-input').forEach(input => {
                        const denom = input.dataset.denom;
                        const originalValue = originalTransactionData.cash_breakdown[denom];
                        if (originalValue !== undefined) {
                            input.value = originalValue;
                            const span = input.closest('.editable-cell').querySelector('.display-value');
                            span.innerText = originalValue;
                        }
                    });
                }
            });
            
            reportTableContainer.querySelectorAll('tr[data-id]').forEach(row => {
                if (reportType === 'daily_summary') updateDailySummaryRow(row);
                if (reportType === 'daily_cash_summary') updateDailyCashSummaryRow(row);
                if (reportType === 'transaction_log') updateTransactionLogRow(row);
                if (reportType === 'daily_cash_check') updateDailyCashCheckRow(row);
            });
            
            toggleEditMode(false);
        });
    }
    
    const editableForm = document.getElementById(`editable-form-${reportType}`);
    if (editableForm) {
        editableForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            let payload = [];

            if (reportType === 'daily_summary') {
                 reportTableContainer.querySelectorAll('tbody tr[data-id]').forEach(row => {
                    const rowData = {
                        id: row.dataset.id,
                        opening_cash: getCleanNumber(row.querySelector('[data-field="opening_cash"] .editable-input').value)
                    };
                    payload.push(rowData);
                 });
            } else if (reportType === 'daily_cash_check') {
                reportTableContainer.querySelectorAll('tbody tr[data-id]').forEach(row => {
                    const rowData = { id: row.dataset.id, cash_breakdown: {} };
                    row.querySelectorAll('.cash-breakdown-input').forEach(input => {
                        rowData.cash_breakdown[input.dataset.denom] = getCleanNumber(input.value);
                    });
                    payload.push(rowData);
                });
            } else if (reportType === 'transaction_log') {
                 const updatedData = {};
                 reportTableContainer.querySelectorAll('tbody tr[data-id]').forEach(row => {
                     const rowId = row.dataset.id;
                     if (!updatedData[rowId]) {
                         updatedData[rowId] = { id: rowId, items: [] };
                         const cashReceivedCell = row.querySelector('[data-field="cash_received"]');
                         if (cashReceivedCell) {
                             updatedData[rowId].cash_received = getCleanNumber(cashReceivedCell.querySelector('.editable-input').value);
                         }
                     }
                     
                     const itemCell = row.querySelector('[data-item-id]');
                     const categoryCell = row.querySelector('[data-field="category"]');
                     if (itemCell) {
                         const itemId = itemCell.dataset.itemId;
                         const priceInput = itemCell.querySelector('.editable-input');
                         const categorySelect = categoryCell.querySelector('.editable-select');
                         updatedData[rowId].items.push({
                             id: itemId,
                             price: getCleanNumber(priceInput.value),
                             category_id: categorySelect.value
                         });
                     }
                 });
                 payload = Object.values(updatedData);
            }
            
            try {
                const response = await fetch(editableForm.action, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name="csrf_token"]').value
                    },
                    body: JSON.stringify(payload)
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

    reportTableContainer.addEventListener('change', function(event) {
        const select = event.target;
        if (select.classList.contains('editable-select')) {
            const displayValueSpan = select.closest('.editable-cell').querySelector('.display-value');
            const newCategoryId = select.value;
            displayValueSpan.innerText = select.options[select.selectedIndex].text;
            select.closest('.editable-cell').dataset.categoryId = newCategoryId;
            
            const itemTypeCell = select.closest('tr').querySelector('td:nth-child(4) .badge');
            const itemType = categoryTypeMap[newCategoryId];

            if (itemTypeCell && itemType) {
                if (itemType.includes('discount')) {
                    itemTypeCell.classList.remove('bg-success');
                    itemTypeCell.classList.add('bg-danger');
                    itemTypeCell.innerText = '折扣';
                } else {
                    itemTypeCell.classList.remove('bg-danger');
                    itemTypeCell.classList.add('bg-success');
                    itemTypeCell.innerText = '商品';
                }
            }

            const row = select.closest('tr');
            if (reportType === 'transaction_log') {
                 updateTransactionLogRow(row);
            }
        }
    });
    
    toggleEditMode(false);
});