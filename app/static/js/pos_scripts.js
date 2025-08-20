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

    // --- 狀態變數 ---
    let expression = [];
    let currentInput = '0';
    let transactionItems = [];
    let transactionTotal = 0;
    let inPaymentMode = false;
    let isReadyForNewInput = false;
    let resetTimeout = null;

    // --- 核心顯示與計算 ---
    function updateDisplay() {
        const itemsStr = transactionItems.map(item => `${item.displayText}${item.categoryName}`).join('+').replace(/\+-/g, '-');
        const expressionStr = expression.join(' ');
        const operator = (expression.length > 0 && itemsStr) ? ' + ' : '';
        displayExpression.innerText = `${itemsStr}${operator}${expressionStr}`;
        displayExpression.scrollLeft = displayExpression.scrollWidth;
        displayMain.innerText = parseFloat(currentInput).toLocaleString();

        if (inPaymentMode) {
            displaySub.innerText = `應收: ${transactionTotal.toLocaleString()} / 請輸入收款金額`;
            const amountPaid = parseFloat(currentInput);
            checkoutBtn.disabled = isNaN(amountPaid) || amountPaid < transactionTotal;
            donationBtn.disabled = false;
            otherIncomeBtn.disabled = false;
        } else {
            const total = calculateCurrentTotal();
            displaySub.innerText = `小計: ${total.toLocaleString()}`;
            const isPristine = currentInput === '0' && expression.length === 0 && transactionItems.length === 0;
            equalsBtn.disabled = isPristine;
            donationBtn.disabled = isPristine;
            otherIncomeBtn.disabled = isPristine;
        }
    }

    function calculateCurrentTotal() {
        let itemsTotal = transactionItems.reduce((sum, item) => sum + item.price, 0);
        try {
            const tempExpression = [...expression, currentInput];
            const currentExpressionValue = safeCalculate(tempExpression.join(' '));
            return itemsTotal + currentExpressionValue;
        } catch { return itemsTotal; }
    }

    // --- 狀態切換 ---
    function enterPaymentMode() {
        inPaymentMode = true;
        isReadyForNewInput = true;
        transactionTotal = calculateCurrentTotal();
        categoryButtons.forEach(btn => btn.disabled = true);
        operatorButtons.forEach(btn => btn.disabled = true);
        equalsBtn.style.display = 'none';
        checkoutBtn.style.display = 'block';
        currentInput = transactionTotal.toString();
        updateDisplay();
    }

    function exitPaymentMode(amountPaid) {
        const change = amountPaid - transactionTotal;
        displaySub.innerText = `找零: ${change.toLocaleString()} (收到 ${amountPaid.toLocaleString()})`;
        updateReceiptForCheckout();
        resetTimeout = setTimeout(resetCalculator, 10000);
    }

    function resetCalculator() {
        if (resetTimeout) { clearTimeout(resetTimeout); resetTimeout = null; }
        inPaymentMode = false;
        isReadyForNewInput = false;
        expression = [];
        currentInput = '0';
        transactionItems = [];
        transactionTotal = 0;
        receiptDetails.innerHTML = '<div class="text-center text-muted m-auto">暫無商品</div>';
        allButtons.forEach(btn => btn.disabled = false);
        equalsBtn.style.display = 'block';
        checkoutBtn.style.display = 'none';
        updateDisplay();
    }

    // --- 核心按鈕處理函式 ---
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
        updateDisplay();
    });

    const handleOperator = interruptResetAndContinue(function (op) {
        if (inPaymentMode) return;
        if (currentInput === '0' && expression.length > 0 && ['+', '-', '*', '/'].includes(expression[expression.length - 1])) {
            expression[expression.length - 1] = op;
        } else {
            expression.push(currentInput);
            expression.push(op);
            currentInput = '0';
        }
        updateDisplay();
    });

    const handleCategory = interruptResetAndContinue(function (categoryId, categoryName) {
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
        if (categoryName.includes('折扣')) {
            unitPrice = -Math.abs(unitPrice);
        }
        totalPrice = quantity * unitPrice;
        if (totalPrice === 0 && !categoryName.includes('折扣')) return;
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
        updateDisplay();
    });

    // --- ** 最終修正點：恢復「復原」按鈕的正確邏輯 ** ---
    // const handleUndo = interruptResetAndContinue(function() {
    //     if (inPaymentMode) return;

    //     const hasActiveEntry = (currentInput !== '0' || expression.length > 0);

    //     if (hasActiveEntry) {
    //         currentInput = '0';
    //         expression = [];
    //     } 
    //     else if (transactionItems.length > 0) {
    //         transactionItems.pop();
    //         updateReceipt();
    //     }

    //     updateDisplay();
    // });

    // --- ** 最終修正點：恢復「復原」按鈕的正確邏輯 ** ---
    const handleUndo = interruptResetAndContinue(function () {
        if (inPaymentMode) return;

        // 判斷當前是否有正在輸入的數字或運算式
        const hasActiveEntry = (currentInput !== '0' || expression.length > 0);

        if (hasActiveEntry) {
            // 第一階段：僅清除當前輸入
            currentInput = '0';
            expression = [];
        }
        else if (transactionItems.length > 0) {
            // 第二階段：如果沒有輸入，則移除最後一個交易品項
            transactionItems.pop();
            updateReceipt(); // 更新右側明細
        }

        // 無論執行哪個階段，都重新計算並更新一次顯示
        updateDisplay();
    });

    const handleBackspace = interruptResetAndContinue(function () {
        if (currentInput.length > 1) { currentInput = currentInput.slice(0, -1); }
        else { currentInput = '0'; }
        updateDisplay();
    });

    async function handleCheckout() {
        const amountPaid = parseFloat(currentInput);
        if (checkoutBtn.disabled) return;
        await sendTransaction();
        exitPaymentMode(amountPaid);
    }

    const handleOtherIncome = interruptResetAndContinue(async function (type) {
        if (!inPaymentMode) {
            const amount = parseFloat(currentInput);
            if (isNaN(amount) || amount <= 0) return;
            await sendOtherIncome(amount, type);
            updateReceiptForOtherIncome(amount, type);
            resetTimeout = setTimeout(resetCalculator, 10000);
        } else {
            const amountPaid = parseFloat(currentInput);
            const finalAmountPaid = (isNaN(amountPaid) || amountPaid < transactionTotal) ? transactionTotal : amountPaid;
            await sendOtherIncome(transactionTotal, type);
            const change = finalAmountPaid - transactionTotal;
            displaySub.innerText = `找零: ${change.toLocaleString()} (收到 ${finalAmountPaid.toLocaleString()})`;
            updateReceiptForOtherIncome(transactionTotal, type, true);
            resetTimeout = setTimeout(resetCalculator, 10000);
        }
    });

    function updateReceipt() {
        if (transactionItems.length === 0) {
            receiptDetails.innerHTML = '<div class="text-center text-muted m-auto">暫無商品</div>';
        } else {
            let itemsHtml = transactionItems.map(item =>
                // 保持原本的商品行樣式
                `<div class="d-flex justify-content-between align-items-center px-3 py-1">
                <span>${item.categoryName}</span>
                <span class="${item.price < 0 ? 'text-danger' : ''}">${item.price.toLocaleString()}</span>
            </div>`
            ).join('');
            // 在外面包裹一個和結帳時結構相同的父容器
            receiptDetails.innerHTML = `
            <div class="p-2 d-flex flex-column h-100">
                <div class="flex-grow-1">${itemsHtml}</div>
            </div>`;
        }
        receiptDetails.scrollTop = receiptDetails.scrollHeight;
    }

    function updateReceiptForCheckout() {
        const amountPaid = parseFloat(currentInput);
        const change = amountPaid - transactionTotal;
        const positiveItemsTotal = transactionItems.filter(item => item.price > 0).reduce((sum, item) => sum + item.price, 0);
        const negativeItems = transactionItems.filter(item => item.price < 0);
        let discountHtml = '<div style="height: 1.5rem;"></div>';
        if (negativeItems.length > 0) {
            discountHtml = negativeItems.map(item =>
                `<div class="d-flex justify-content-between px-3 py-1">
                <span>${item.categoryName}</span>
                <span class="text-danger">${item.price.toLocaleString()}</span>
            </div>`
            ).join('');
        }
        // 確認這裡的父容器和上面修改後的一致
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
        receiptDetails.innerHTML = `
            <div class="text-center p-3 m-auto">
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
                if (document.getElementById("donation-total")) {
                    document.getElementById("donation-total").innerText = `$ ${Math.round(result.donation_total).toLocaleString()}`;
                }
                if (document.getElementById("other-total")) {
                    document.getElementById("other-total").innerText = `$ ${Math.round(result.other_total).toLocaleString()}`;
                }
                displaySub.innerText = type === 'donation' ? "感謝您的愛心捐款！" : "已記錄其他收入";
            } else { displaySub.innerText = `記錄失敗: ${result.error}`; }
        } catch (error) { console.error("記錄其他收入時發生錯誤:", error); displaySub.innerText = "記錄失敗，請檢查網路連線。"; }
    }

    // --- 事件綁定 ---
    numberButtons.forEach(btn => btn.addEventListener('click', () => handleNumber(btn.dataset.value)));
    operatorButtons.forEach(btn => btn.addEventListener('click', () => handleOperator(btn.dataset.value)));
    categoryButtons.forEach(btn => btn.addEventListener('click', () => handleCategory(btn.dataset.id, btn.dataset.name)));
    equalsBtn.addEventListener('click', enterPaymentMode);
    checkoutBtn.addEventListener('click', handleCheckout);
    clearBtn.addEventListener('click', interruptResetAndContinue(resetCalculator));
    undoBtn.addEventListener('click', handleUndo);
    backspaceBtn.addEventListener('click', handleBackspace);
    donationBtn.addEventListener('click', () => handleOtherIncome('donation'));
    otherIncomeBtn.addEventListener('click', () => handleOtherIncome('other'));

    // --- 初始化 ---
    resetCalculator();
});