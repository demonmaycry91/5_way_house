document.addEventListener("DOMContentLoaded", function () {
    // --- DOM 元素 ---
    const displayExpression = document.getElementById("display-expression");
    const displayMain = document.getElementById("display-main");
    const displaySub = document.getElementById("display-sub");
    const receiptDetails = document.getElementById("receipt-details");

    const allButtons = document.querySelectorAll(".calc-btn, .category-btn");
    const numberButtons = document.querySelectorAll(".number-btn");
    const operatorButtons = document.querySelectorAll(".operator-btn");
    const categoryButtons = document.querySelectorAll(".category-btn");

    const equalsBtn = document.getElementById("equals-btn");
    const checkoutBtn = document.getElementById("checkout-btn");
    const clearBtn = document.querySelector('[data-action="clear"]');
    const undoBtn = document.querySelector('[data-action="undo"]');
    const backspaceBtn = document.querySelector('[data-action="backspace"]');
    const donationBtn = document.getElementById("donation-btn");
    const otherIncomeBtn = document.getElementById("other-income-btn");
    
    const responsiveElements = document.querySelectorAll('.responsive-h3');

    // --- 狀態變數 ---
    let expression = [];
    let currentInput = '0';
    let transactionItems = [];
    let subtotal = 0;
    let isReadyForNewInput = false;
    let resetTimeout = null;

    let inPaymentMode = false;
    let inDiscountMode = false;
    let discountInfo = {};

    // --- [全新修正版] 智慧調整字體大小 ---
    function adjustFontSizes() {
        if (responsiveElements.length === 0) return;
        const maxFontSizeRem = 1.75;
        const minFontSizeRem = 0.75;
        responsiveElements.forEach(el => { el.style.fontSize = `${maxFontSizeRem}rem`; });
        let maxOverflowRatio = 1.0;
        responsiveElements.forEach(el => {
            if (el.offsetWidth > 0) {
                const ratio = el.scrollWidth / el.offsetWidth;
                if (ratio > maxOverflowRatio) { maxOverflowRatio = ratio; }
            }
        });
        let newFontSizeRem = maxFontSizeRem;
        if (maxOverflowRatio > 1.0) { newFontSizeRem = maxFontSizeRem / maxOverflowRatio; }
        if (newFontSizeRem < minFontSizeRem) { newFontSizeRem = minFontSizeRem; }
        responsiveElements.forEach(el => { el.style.fontSize = `${newFontSizeRem}rem`; });
    }

    // --- 統一格式化函式 ---
    function reformatInitialValues() {
        responsiveElements.forEach(el => {
            const text = el.innerText.replace(/[^0-9.]/g, '');
            const number = parseFloat(text) || 0;
            if (el.id === 'total-transactions' || el.id === 'total-items') {
                el.innerText = number.toLocaleString('en-US');
            } else {
                el.innerText = `$ ${number.toLocaleString('en-US')}`;
            }
        });
    }

    function calculateCurrentTotal() {
        let itemsTotal = transactionItems.reduce((sum, item) => sum + item.price, 0);
        try {
            const tempExpression = [...expression, currentInput];
            const currentExpressionValue = safeCalculate(tempExpression.join(' '));
            return itemsTotal + currentExpressionValue;
        } catch { return itemsTotal; }
    }

    function enterPaymentMode(finalTotal) {
        inPaymentMode = true;
        inDiscountMode = false;
        isReadyForNewInput = true;

        equalsBtn.style.display = 'none';
        checkoutBtn.style.display = 'block';

        // 啟用所有包含「鄉親卡」或「全場」的類別按鈕，禁用其他
        categoryButtons.forEach(btn => {
            const name = btn.dataset.name;
            if (name.includes('鄉親卡') || name.includes('全場')) {
                btn.disabled = false;
            } else {
                btn.disabled = true;
            }
        });

        operatorButtons.forEach(btn => btn.disabled = true);
        donationBtn.disabled = false;
        otherIncomeBtn.disabled = false;

        currentInput = finalTotal.toString();
        displayMain.innerText = finalTotal.toLocaleString();
        displaySub.innerText = `應收: ${finalTotal.toLocaleString()} / 請輸入收款金額`;
    }

    function resetCalculator() {
        if (resetTimeout) { clearTimeout(resetTimeout); resetTimeout = null; }

        expression = [];
        currentInput = '0';
        transactionItems = [];
        subtotal = 0;
        isReadyForNewInput = false;
        inPaymentMode = false;
        inDiscountMode = false;
        discountInfo = {};

        receiptDetails.className = 'd-flex justify-content-center align-items-center h-100';
        receiptDetails.innerHTML = '<span class="text-muted">暫無商品</span>';

        allButtons.forEach(btn => btn.disabled = false);
        equalsBtn.style.display = 'block';
        checkoutBtn.style.display = 'none';

        displayMain.innerText = '0';
        displaySub.innerText = '小計: 0';
        displayExpression.innerText = '';
    }

    function interruptResetAndContinue(handler) {
        return function (...args) {
            if (resetTimeout) {
                resetCalculator();
            }
            handler(...args);
        }
    }

    const handleNumber = interruptResetAndContinue(function (value) {
        if (isReadyForNewInput) {
            currentInput = value === '.' ? '0.' : value;
            isReadyForNewInput = false;
        } else {
            if (currentInput === '0' && value !== '00' && value !== '.') { currentInput = value; }
            else {
                if (value === '.' && currentInput.includes('.')) return;
                if (currentInput === '0' && value === '00') return;
                if (currentInput.length > 13) return;
                currentInput += value;
            }
        }
        displayMain.innerText = parseFloat(currentInput).toLocaleString();
    });

    const handleOperator = interruptResetAndContinue(function (op) {
        if (inPaymentMode) return;
        if (currentInput === '0' && expression.length > 0 && ['+', '-', '*', '/'].includes(expression[expression.length - 1])) {
            expression[expression.length - 1] = op;
        } else {
            expression.push(currentInput);
            expression.push(op);
            currentInput = '0';
            isReadyForNewInput = true;
        }
        displayExpression.innerText = [...transactionItems.map(i => i.displayText), ...expression].join(' ');
    });

    const handleCategoryClick = interruptResetAndContinue(function (categoryId, categoryName) {
        const isDiscountButton = categoryName.includes('鄉親卡') || categoryName.includes('全場');

        if (isDiscountButton) {
            handleDiscount(categoryId, categoryName);
        } else {
            addTransactionItem(categoryId, categoryName);
        }
    });

    function addTransactionItem(categoryId, categoryName) {
        if (inPaymentMode) return;
        const fullExpression = [...expression, currentInput].join(' ');
        let quantity = 1;
        let unitPrice = 0;
        let totalPrice = 0;
        let displayText = '';
        if (fullExpression.includes('*')) {
            const parts = fullExpression.split('*');
            if (parts.length === 2 && !/[+\-/]/.test(parts[0]) && !/[+\-/]/.test(parts[1])) {
                const parsedQty = parseInt(safeCalculate(parts[0]), 10);
                const parsedPrice = safeCalculate(parts[1]);
                if (!isNaN(parsedQty) && parsedQty > 0) {
                    quantity = parsedQty;
                    unitPrice = parsedPrice;
                    displayText = `${quantity}*${unitPrice}`;
                }
            }
        }
        if (displayText === '') {
            try {
                unitPrice = safeCalculate(fullExpression);
                displayText = unitPrice.toString();
            } catch (e) {
                displaySub.innerText = "計算錯誤"; return;
            }
        }
        if (categoryName.includes('折扣') && !categoryName.includes('鄉親卡') && !categoryName.includes('全場')) {
            unitPrice = -Math.abs(unitPrice);
        }

        const isCouponDiscount = categoryName.includes('折扣') && !categoryName.includes('鄉親卡') && !categoryName.includes('全場');
        
        if (isCouponDiscount) {
            unitPrice = -Math.abs(unitPrice);
            // 如果是折扣卷，displayText 應該直接就是負數金額
            // 這確保了 displayText 和 price 的符號一致
            displayText = unitPrice.toString();
        }

        totalPrice = quantity * unitPrice;
        if (totalPrice === 0) {
            // 無論是什麼類別，只要金額為 0 就直接返回，不做任何事
            return;
        }
        transactionItems.push({
            price: totalPrice,
            unitPrice: unitPrice,
            quantity: quantity,
            category_id: categoryId,
            categoryName: categoryName,
            displayText: displayText
        });
        expression = [];
        currentInput = '0';
        updateReceipt();
        displaySub.innerText = `小計: ${calculateCurrentTotal().toLocaleString()}`;

        // --- ↓↓↓ 核心修正點 (第二部分) ↓↓↓ ---
        // 更新算式組合邏輯，以正確處理負號
        displayExpression.innerText = transactionItems
            .map(i => i.displayText)
            .join('+')
            .replace(/\+-/g, ' - ');
        // --- ↑↑↑ 修正結束 ↑↑↑ ---

        
    }

    const handleEquals = interruptResetAndContinue(function () {
        if (inDiscountMode) {
            const discountValue = parseFloat(currentInput);
            if (isNaN(discountValue) || discountValue < 0 || discountValue > 100) {
                displaySub.innerText = "錯誤：請輸入有效的折扣數字";
                return;
            }
            let discountMultiplier = discountValue / 100;
            if (discountValue < 10) {
                discountMultiplier = discountValue / 10;
            }
            const discountAmount = -Math.round(subtotal * (1 - discountMultiplier));
            transactionItems = transactionItems.filter(item => item.category_id !== discountInfo.categoryId);
            transactionItems.push({
                price: discountAmount,
                unitPrice: discountAmount,
                quantity: 1,
                category_id: discountInfo.categoryId,
                categoryName: discountInfo.categoryName,
                displayText: `${discountValue}折`
            });
            const finalTotal = subtotal + discountAmount;
            updateReceipt();
            enterPaymentMode(finalTotal);
        } else if (!inPaymentMode) {
            subtotal = calculateCurrentTotal();
            expression = [];
            currentInput = '0';
            enterPaymentMode(subtotal);
        }
    });

    function handleDiscount(categoryId, categoryName) {
        if (!inPaymentMode) return;
        
        discountInfo = {
            categoryId: categoryId,
            categoryName: categoryName
        };
        
        inDiscountMode = true;
        isReadyForNewInput = true;
        currentInput = '0';

        displaySub.innerText = `請輸入折扣數 (例如 9折 輸入 9, 88折 輸入 88)`;
        
        equalsBtn.style.display = 'block';
        checkoutBtn.style.display = 'none';
        
        categoryButtons.forEach(btn => btn.disabled = true);
    }

    const handleUndo = interruptResetAndContinue(function () {
        if (inPaymentMode) return;
        const hasActiveEntry = (currentInput !== '0' || expression.length > 0);
        if (hasActiveEntry) {
            currentInput = '0';
            expression = [];
        }
        else if (transactionItems.length > 0) {
            transactionItems.pop();
            updateReceipt();
        }
        // --- ↓↓↓ 核心修正點 ↓↓↓ ---
        displayExpression.innerText = transactionItems
            .map(i => i.displayText)
            .join('+')
            .replace(/\+-/g, ' - ');
        // --- ↑↑↑ 修正結束 ↑↑↑ ---

        displayMain.innerText = currentInput;
        displaySub.innerText = `小計: ${calculateCurrentTotal().toLocaleString()}`;
    });

    const handleBackspace = interruptResetAndContinue(function () {
        if (currentInput.length > 1) { currentInput = currentInput.slice(0, -1); }
        else { currentInput = '0'; }
        displayMain.innerText = parseFloat(currentInput).toLocaleString();
    });

    async function handleCheckout() {
        const amountPaid = parseFloat(currentInput);
        const finalTotalStr = displayMain.innerText.replace(/[^0-9.-]+/g, "");
        const finalTotal = parseFloat(finalTotalStr);

        if (isNaN(amountPaid) || amountPaid < finalTotal) {
            displaySub.innerText = `金額不足，應收: ${finalTotal.toLocaleString()}`;
            return;
        }

        await sendTransaction();

        const change = amountPaid - finalTotal;
        displaySub.innerText = `找零: ${change.toLocaleString()} (收到 ${amountPaid.toLocaleString()})`;
        updateReceiptForCheckout(amountPaid, finalTotal);
        resetTimeout = setTimeout(resetCalculator, 10000);
    }

    const handleOtherIncome = interruptResetAndContinue(async function (type) {
        let amount;
        let isFromTransaction = false;
        if (inPaymentMode) {
            const finalTotalStr = displayMain.innerText.replace(/[^0-9.-]+/g, "");
            amount = parseFloat(finalTotalStr);
            isFromTransaction = true;
        } else {
            amount = parseFloat(currentInput);
        }

        if (isNaN(amount) || amount <= 0) return;

        await sendOtherIncome(amount, type);
        updateReceiptForOtherIncome(amount, type, isFromTransaction);
        resetTimeout = setTimeout(resetCalculator, 10000);
    });

    function updateReceipt() {
        if (transactionItems.length === 0) {
            receiptDetails.className = 'd-flex justify-content-center align-items-center h-100';
            receiptDetails.innerHTML = '<span class="text-muted">暫無商品</span>';
        } else {
            receiptDetails.className = '';
            let itemsHtml = transactionItems.map(item =>
                `<div class="d-flex justify-content-between align-items-center px-3 py-1">
                    <span>${item.categoryName}</span>
                    <span class="${item.price < 0 ? 'text-danger' : ''}">${item.price.toLocaleString()}</span>
                </div>`
            ).join('');
            receiptDetails.innerHTML = `
                <div class="p-2 d-flex flex-column h-100">
                    <div class="flex-grow-1">${itemsHtml}</div>
                </div>`;
        }
        receiptDetails.scrollTop = receiptDetails.scrollHeight;
    }

    function updateReceiptForCheckout(amountPaid, transactionTotal) {
        const change = amountPaid - transactionTotal;
        const positiveItemsTotal = transactionItems.filter(item => item.price > 0).reduce((sum, item) => sum + item.price, 0);
        // --- ↓↓↓ 這是全新的、最核心的版面排版邏輯 ↓↓↓ ---

        // 1. 將所有折扣項目（價格為負數的）篩選出來
        const allDiscounts = transactionItems.filter(item => item.price < 0);

        // 2. 根據您的要求，將折扣分為兩類：「折扣卷」和「百分比折扣」
        const couponDiscounts = allDiscounts.filter(d => !d.categoryName.includes('鄉親卡') && !d.categoryName.includes('全場'));
        const percentageDiscounts = allDiscounts.filter(d => d.categoryName.includes('鄉親卡') || d.categoryName.includes('全場'));
        
        // 3. 按照您指定的順序（先折扣卷，再百分比折扣）合併
        const sortedDiscounts = [...couponDiscounts, ...percentageDiscounts];

        // 4. 創建一個代表 5 個「折扣槽位」的空陣列
        const MAX_DISCOUNT_SLOTS = 3;
        const discountSlots = new Array(MAX_DISCOUNT_SLOTS).fill(null);

        // 5. 從下往上（從索引 4 開始），將折扣項目填入槽位中
        let currentSlotIndex = MAX_DISCOUNT_SLOTS - 1; 
        for (let i = sortedDiscounts.length - 1; i >= 0; i--) {
            if (currentSlotIndex >= 0) {
                discountSlots[currentSlotIndex] = sortedDiscounts[i];
                currentSlotIndex--;
            }
        }

        // 6. 根據槽位的內容，生成對應的 HTML
        const discountHtml = discountSlots.map(slot => {
            if (slot) {
                // 如果槽位有內容，則顯示折扣資訊
                return `<div class="d-flex justify-content-between px-3 py-1">
                            <span>${slot.categoryName}</span>
                            <span class="text-danger">${slot.price.toLocaleString()}</span>
                        </div>`;
            } else {
                // 如果槽位是空的，則顯示一個佔位的空白行，以維持版面整齊
                return `<div class="py-1" style="height: 2.1rem;">&nbsp;</div>`; 
            }
        }).join('');
        
        // --- ↑↑↑ 核心邏輯結束 ↑↑↑ ---
        receiptDetails.className = '';
        receiptDetails.innerHTML = `
            <div class="p-2 d-flex flex-column h-100">
                <div class="d-flex justify-content-between px-3 py-1">
                    <span>商品總計</span>
                    <span>${positiveItemsTotal.toLocaleString()}</span>
                </div>
                ${discountHtml}
                <hr class="my-1">
                <div class="flex-grow-1"></div>
                <div>
                    <div class="d-flex justify-content-between fw-bold px-3 py-1">
                        <span>應收金額</span>
                        <span>${transactionTotal.toLocaleString()}</span>
                    </div>
                    <div class="d-flex justify-content-between px-3 py-1">
                        <span>實收現金</span>
                        <span>${amountPaid.toLocaleString()}</span>
                    </div>
                    <div class="d-flex justify-content-between px-3 py-1">
                        <span>找零</span>
                        <span>${change.toLocaleString()}</span>
                    </div>
                </div>
            </div>`;
    }

    function updateReceiptForOtherIncome(amount, type, isFromTransaction = false) {
        let title = type === 'donation' ? "愛心捐款" : "其他收入";
        if (isFromTransaction) {
            title = type === 'donation' ? "交易轉捐款" : "交易轉其他";
        }
        receiptDetails.className = 'd-flex justify-content-center align-items-center h-100';
        receiptDetails.innerHTML = `
            <div class="text-center p-3">
                <h4 class="fw-bold mb-2">${title}</h4>
                <p class="text-muted small mb-3">您的每一份支持，都是改變的力量</p>
                <hr class="my-2">
                <div class="d-flex justify-content-between align-items-center fs-4 mt-3 px-3">
                    <span class="text-success fw-bold">NT$</span>
                    <span class="fw-bold">${amount.toLocaleString()}</span>
                </div>
            </div>`;
    }

    function safeCalculate(exprStr) {
        let sanitizedExpr = String(exprStr).replace(/[^0-9.+\-*/().\s]/g, '');
        if (!sanitizedExpr.trim()) return 0;
        if (['+', '-', '*', '/'].includes(sanitizedExpr.trim().slice(-1))) {
            sanitizedExpr = sanitizedExpr.trim().slice(0, -1);
        }
        if (sanitizedExpr.trim() === '') return 0;
        return new Function('return ' + sanitizedExpr)();
    }

    async function sendTransaction() {
        const expandedItems = [];
        transactionItems.forEach(item => {
            for (let i = 0; i < item.quantity; i++) {
                expandedItems.push({
                    price: item.unitPrice,
                    category_id: item.category_id
                });
            }
        });
        try {
            const response = await fetch("/cashier/record_transaction", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    location_slug: POS_LOCATION_SLUG,
                    items: expandedItems
                }),
            });
            if (!response.ok) throw new Error("網路回應不正確");
            const result = await response.json();
            if (result.success) {
                if (document.getElementById("total-sales")) {
                    document.getElementById("total-sales").innerText = `$ ${Math.round(result.total_sales).toLocaleString()}`;
                    document.getElementById("total-transactions").innerText = result.total_transactions;
                    document.getElementById("total-items").innerText = result.total_items;
                    adjustFontSizes();
                }
            } else { displaySub.innerText = `傳送失敗: ${result.error}`; }
        } catch (error) { console.error("結帳時發生錯誤:", error); displaySub.innerText = "傳送失敗"; }
    }

    async function sendOtherIncome(amount, type) {
        try {
            const response = await fetch("/cashier/record_other_income", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ location_slug: POS_LOCATION_SLUG, amount: amount, type: type }),
            });
            if (!response.ok) throw new Error("網路回應不正確");
            const result = await response.json();
            if (result.success) {
                const donationTotalEl = document.getElementById("donation-total");
                const otherTotalEl = document.getElementById("other-total");
                const otherIncomeTotalEl = document.getElementById("other-income-total");

                if (donationTotalEl) {
                    donationTotalEl.innerText = `$ ${Math.round(result.donation_total).toLocaleString()}`;
                }
                if (otherTotalEl) {
                    otherTotalEl.innerText = `$ ${Math.round(result.other_total).toLocaleString()}`;
                }
                if (otherIncomeTotalEl) {
                    const totalOtherIncome = (result.donation_total || 0) + (result.other_total || 0);
                    otherIncomeTotalEl.innerText = `$ ${Math.round(totalOtherIncome).toLocaleString()}`;
                }

                adjustFontSizes();

                displaySub.innerText = type === 'donation' ? "感謝您的愛心捐款！" : "已記錄其他收入";
            } else { displaySub.innerText = `記錄失敗: ${result.error}`; }
        } catch (error) { console.error("記錄其他收入時發生錯誤:", error); displaySub.innerText = "記錄失敗，請檢查網路連線。"; }
    }

    // --- 事件綁定 ---
    numberButtons.forEach(btn => btn.addEventListener('click', () => handleNumber(btn.dataset.value)));
    operatorButtons.forEach(btn => btn.addEventListener('click', () => handleOperator(btn.dataset.value)));
    // 核心修正：所有類別按鈕都綁定到同一個智慧型處理函式
    categoryButtons.forEach(btn => btn.addEventListener('click', () => handleCategoryClick(btn.dataset.id, btn.dataset.name)));
    equalsBtn.addEventListener('click', handleEquals);
    checkoutBtn.addEventListener('click', handleCheckout);
    clearBtn.addEventListener('click', interruptResetAndContinue(resetCalculator));
    undoBtn.addEventListener('click', handleUndo);
    backspaceBtn.addEventListener('click', handleBackspace);
    donationBtn.addEventListener('click', () => handleOtherIncome('donation'));
    otherIncomeBtn.addEventListener('click', () => handleOtherIncome('other'));
    
    // --- 初始化 ---
    resetCalculator();
    reformatInitialValues();
    adjustFontSizes();
    window.addEventListener('resize', adjustFontSizes);
});