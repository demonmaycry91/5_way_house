document.addEventListener("DOMContentLoaded", function () {
    // --- DOM 元素 ---
    const displayExpression = document.getElementById("display-expression");
    const displayMain = document.getElementById("display-main");
    const displaySub = document.getElementById("display-sub");
    const receiptDetails = document.getElementById("receipt-details");
    const categoryButtons = document.querySelectorAll(".category-btn");
    const equalsBtn = document.getElementById("equals-btn");
    const checkoutBtn = document.getElementById("checkout-btn");
    const donationBtn = document.getElementById("donation-btn");
    const otherIncomeBtn = document.getElementById("other-income-btn");

    // --- 狀態變數 ---
    let expression = [];
    let currentInput = '0';
    let transactionItems = [];
    let isReadyForNewInput = false;
    let inPaymentMode = false;
    let activeDiscountMode = null;
    let finalTotalForPayment = 0;
    let isTransactionComplete = false;
    
    // =================================================================
    // SECTION 1: 核心計算與狀態管理函式
    // =================================================================

    function resetCalculator() {
        expression = [];
        currentInput = '0';
        transactionItems = [];
        isReadyForNewInput = false;
        inPaymentMode = false;
        activeDiscountMode = null;
        finalTotalForPayment = 0;
        isTransactionComplete = false;
        
        categoryButtons.forEach(btn => {
            if (btn.dataset.type === 'discount_percent') {
                btn.disabled = true;
            } else {
                btn.disabled = false;
            }
        });
        document.querySelectorAll(".calc-btn, #donation-btn, #other-income-btn").forEach(btn => btn.disabled = false);

        equalsBtn.style.display = 'block';
        checkoutBtn.style.display = 'none';

        updateReceipt();
        updateDisplay();
    }

    function checkAndResetAfterTransaction() {
        if (isTransactionComplete) {
            resetCalculator();
            return true;
        }
        return false;
    }

    function updateDisplay(subText = null) {
        const mainValue = parseFloat(currentInput) || 0;
        displayMain.innerText = mainValue.toLocaleString('en-US', { maximumFractionDigits: 2 });
    
        // --- ↓↓↓ 這是本次修正的核心 (顯示邏輯) ↓↓↓ ---
        if (inPaymentMode || activeDiscountMode) {
            // 進入結帳或折扣模式時，上方表達式應顯示小計
            const total = calculateCurrentTotal();
            displayExpression.innerText = `小計: ${total.toLocaleString('en-US')}`;
        } else {
            // 正常登錄商品時，顯示完整算式
            const itemsText = transactionItems.map(item => item.displayText).join(' + ');
            const currentExpressionText = [...expression, (currentInput !== '0' || expression.length > 0) ? currentInput : ''].join(' ');
            const fullExpression = [itemsText, currentExpressionText].filter(Boolean).join(' + ').replace(/\+ -/g, '- ');
            displayExpression.innerText = fullExpression;
        }
        // --- ↑↑↑ 修正結束 ↑↑↑ ---

        if (subText) {
            displaySub.innerText = subText;
        } else if (activeDiscountMode) {
            displaySub.innerText = `請輸入折扣數字 (例如 9折 輸入 9)`;
        } else if (inPaymentMode) {
            displaySub.innerText = `應收: ${finalTotalForPayment.toLocaleString('en-US')} / 實收: ${mainValue.toLocaleString('en-US')}`;
        } else {
            const currentTotal = calculateCurrentTotal();
            displaySub.innerText = `小計: ${currentTotal.toLocaleString('en-US')}`;
        }
    }
    
    // --- ↓↓↓ 這是本次修正的核心 (計算邏輯) ↓↓↓ ---
    function calculateCurrentTotal() {
        const itemsTotal = transactionItems.reduce((sum, item) => sum + item.price, 0);

        // 如果正在等待輸入折扣，或已進入最終付款，則小計就是購物籃總額
        if (activeDiscountMode || inPaymentMode) {
            return itemsTotal;
        }
        
        // 只有在第一階段（登錄商品時）才加上當前輸入的數字
        let exprString = [...expression, currentInput].join(' ');
        if (['+', '-', '*', '/'].includes(exprString.trim().slice(-1))) {
            exprString = exprString.trim().slice(0, -1);
        }
        const currentExpressionValue = safeCalculate(exprString);
        return itemsTotal + currentExpressionValue;
    }
    // --- ↑↑↑ 修正結束 ↑↑↑ ---
    
    function safeCalculate(exprStr) {
        try {
            let sanitizedExpr = String(exprStr).replace(/[^0-9.+\-*/().\s]/g, '');
            if (!sanitizedExpr.trim() || ['+', '-', '*', '/'].includes(sanitizedExpr.trim().slice(-1))) {
                sanitizedExpr = sanitizedExpr.trim().slice(0, -1);
            }
            if (sanitizedExpr.trim() === '') return 0;
            return new Function('return ' + sanitizedExpr)();
        } catch { return 0; }
    }
    
    // =================================================================
    // SECTION 2: 按鈕事件處理函式
    // =================================================================

    function handleNumber(value) {
        if (checkAndResetAfterTransaction()) {
            handleNumber(value);
            return;
        }
        if (isReadyForNewInput) {
            currentInput = (value === '.') ? '0.' : value;
            isReadyForNewInput = false;
        } else {
            if (currentInput === '0' && value !== '.' && value !== '00') currentInput = value;
            else if (value === '.' && currentInput.includes('.')) return;
            else if (currentInput.length < 14) currentInput += value;
        }
        updateDisplay();
    }

    function handleOperator(op) {
        if (checkAndResetAfterTransaction()) return;
        if (inPaymentMode || activeDiscountMode) return;
        expression.push(currentInput);
        expression.push(op);
        currentInput = '0';
        isReadyForNewInput = true;
        updateDisplay();
    }

    function handleCategoryClick(btn) {
        if (checkAndResetAfterTransaction()) {
            handleCategoryClick(btn);
            return;
        }
        
        const categoryId = btn.dataset.id;
        const categoryName = btn.dataset.name;
        const categoryType = btn.dataset.type;
        const rules = JSON.parse(btn.dataset.rules);

        if (categoryType === 'discount_percent') {
            activateDiscountPercent(categoryId, categoryName, rules);
            return;
        }
        
        if (inPaymentMode) return;

        switch(categoryType) {
            case 'product': applyProduct(categoryId, categoryName); break;
            case 'discount_fixed': applyDiscountFixed(categoryId, categoryName); break;
            case 'buy_n_get_m': applyBuyNGetM(categoryId, categoryName, rules); break;
            case 'buy_x_get_x_minus_1': applyBuyXGetXMinus1(categoryId, categoryName, rules); break;
            case 'buy_odd_even': applyProgressivePairDiscount(categoryId, categoryName, rules); break;
        }
    }

    function handleEquals() {
        if (checkAndResetAfterTransaction()) return;

        if (activeDiscountMode) {
            applyDiscountPercent();
        } else if (!inPaymentMode) {
            const finalValue = safeCalculate([...expression, currentInput].join(' '));
            if (finalValue !== 0 || (expression.length > 0 && currentInput === '0')) {
                 transactionItems.push({
                    price: finalValue, unitPrice: finalValue, quantity: 1,
                    category_id: null, category_type: 'product',
                    categoryName: "手動輸入", displayText: finalValue.toString()
                });
            }
            expression = [];
            currentInput = '0';
            updateReceipt();
            enterPaymentMode();
        } else {
             enterFinalPaymentStage();
        }
    }
    
    function handleUndo() {
        if (checkAndResetAfterTransaction()) return;
        if (inPaymentMode || activeDiscountMode) return;
        
        const hasActiveEntry = currentInput !== '0' || expression.length > 0;
        if (hasActiveEntry) {
            currentInput = '0';
            expression = [];
        } else if (transactionItems.length > 0) {
            const removedItem = transactionItems.pop();
            recalculateAllActiveDiscounts();
        }
        updateDisplay();
        updateReceipt();
    }
    
    // =================================================================
    // SECTION 3: 折扣演算法
    // =================================================================
    
    function applyProduct(categoryId, categoryName) {
        const value = safeCalculate([...expression, currentInput].join(' '));
        if (value <= 0) return;
        let quantity = 1;
        let unitPrice = value;
        let displayText = value.toString();
        const exprString = [...expression, currentInput].join('');
        if (exprString.includes('*') && !exprString.match(/[+\-\/]/)) {
            const parts = exprString.split('*');
            quantity = parseInt(safeCalculate(parts[0]), 10);
            unitPrice = safeCalculate(parts[1]);
            displayText = `${quantity}*${unitPrice}`;
        }
        transactionItems.push({
            price: quantity * unitPrice, unitPrice, quantity,
            category_id: categoryId, category_type: 'product',
            categoryName, displayText
        });
        expression = [];
        currentInput = '0';
        
        recalculateRelevantDiscounts(categoryId);
        updateReceipt();
        updateDisplay();
    }

    function recalculateRelevantDiscounts(changedCategoryId) {
        const activeDiscounts = transactionItems.filter(item => 
            item.price < 0 && item.rules && (item.rules.target_category_id == changedCategoryId || item.rules.target_category_id == 0)
        );
        activeDiscounts.forEach(discount => {
            const btnDataset = {
                id: discount.category_id, name: discount.originalName,
                type: discount.category_type, rules: JSON.stringify(discount.rules)
            };
            handleCategoryClick({ dataset: btnDataset });
        });
    }

    function recalculateAllActiveDiscounts() {
        const activeDiscounts = transactionItems.filter(item => item.price < 0 && item.rules);
        activeDiscounts.forEach(discount => {
             const btnDataset = {
                id: discount.category_id, name: discount.originalName,
                type: discount.category_type, rules: JSON.stringify(discount.rules)
            };
            handleCategoryClick({ dataset: btnDataset });
        });
    }
    
    function applyDiscountFixed(categoryId, categoryName) {
        const value = safeCalculate([...expression, currentInput].join(' '));
        if (value <= 0) return;
        transactionItems.push({
            price: -value, unitPrice: -value, quantity: 1,
            category_id: categoryId, category_type: 'discount_fixed',
            categoryName, displayText: `-${value}`
        });
        expression = [];
        currentInput = '0';
        updateReceipt();
        updateDisplay();
    }

    function activateDiscountPercent(categoryId, categoryName, rules) {
        if (!inPaymentMode) {
            enterPaymentMode();
        }
        activeDiscountMode = { id: categoryId, name: categoryName, rules: rules };
        isReadyForNewInput = true;
        equalsBtn.style.display = 'block';
        checkoutBtn.style.display = 'none';
        updateDisplay();
    }

    function applyDiscountPercent() {
        if (!activeDiscountMode) return;
        
        const { id, name } = activeDiscountMode;
        const subtotal = calculateCurrentTotal();
        let discountValue = parseFloat(currentInput);
        if (isNaN(discountValue) || discountValue < 0 || discountValue > 100) {
            return updateDisplay("錯誤：請輸入有效的折扣數字 (0-100)");
        }
        const multiplier = (discountValue < 10) ? discountValue / 10 : discountValue / 100;
        const discountAmount = -Math.round(subtotal * (1 - multiplier));
        
        transactionItems = transactionItems.filter(item => item.category_id !== id);
        
        if(discountAmount < 0) {
            transactionItems.push({
                price: discountAmount, unitPrice: discountAmount, quantity: 1,
                category_id: id, category_type: 'discount_percent',
                categoryName: `${name} ${discountValue}折`,
                displayText: `-${Math.abs(discountAmount)}`
            });
        }
        activeDiscountMode = null;
        currentInput = '0';
        updateReceipt();
        enterPaymentMode();
    }

    function applyBuyNGetM(categoryId, categoryName, rules) {
        const { target_category_id, buy_n, get_m_free } = rules;
        const eligibleItems = transactionItems.filter(item => {
            if (target_category_id == 0) return item.price > 0 && item.category_type === 'product';
            return item.category_id == target_category_id && item.price > 0;
        });
        if (eligibleItems.length === 0) { 
            const subText = `不符合「${categoryName}」活動資格`;
            updateDisplay(subText);
            updateReceipt(subText);
            return;
        }
        const totalQuantity = eligibleItems.reduce((sum, item) => sum + item.quantity, 0);
        transactionItems = transactionItems.filter(item => item.category_id !== categoryId);
        if (totalQuantity < buy_n) {
            const subText = `提示: 再購 ${buy_n - totalQuantity} 件享「${categoryName}」`;
            updateDisplay(subText);
            updateReceipt(subText);
            return;
        }
        const numberOfDeals = Math.floor(totalQuantity / buy_n);
        const itemsToDiscount = numberOfDeals * get_m_free;
        const discountAmount = calculateDiscountFromCheapest(eligibleItems, itemsToDiscount);
        if(discountAmount > 0) {
            transactionItems.push({
                price: -discountAmount, unitPrice: -discountAmount, quantity: 1,
                category_id: categoryId, category_type: 'buy_n_get_m',
                categoryName: `${categoryName} (送${itemsToDiscount})`, originalName: categoryName, rules: rules,
                displayText: `-${discountAmount}`
            });
        }
        const remainder = totalQuantity % buy_n;
        const neededForNext = buy_n - remainder;
        let subText = `已套用「${categoryName}」優惠`;
        let promptText = null;
        if (remainder > 0 && neededForNext > 0) {
            promptText = `提示: 再購 ${neededForNext} 件可再享一次優惠`;
            subText = promptText;
        }
        updateReceipt(promptText);
        updateDisplay(subText);
    }
    
    function applyBuyXGetXMinus1(categoryId, categoryName, rules) {
        const { target_category_id } = rules;
        const eligibleItems = transactionItems.filter(item => {
            if (target_category_id == 0) return item.price > 0 && item.category_type === 'product';
            return item.category_id == target_category_id && item.price > 0;
        });
        if (eligibleItems.length === 0) { 
            const subText = `不符合「${categoryName}」活動資格`;
            updateDisplay(subText);
            updateReceipt(subText);
            return;
        }
        const totalQuantity = eligibleItems.reduce((sum, item) => sum + item.quantity, 0);
        transactionItems = transactionItems.filter(item => item.category_id !== categoryId);
        if (totalQuantity < 2) {
            const subText = `提示: ${categoryName} 至少需購買 2 件`;
            updateDisplay(subText);
            updateReceipt(subText);
            return;
        }
        const itemsToDiscount = totalQuantity - 1;
        const discountAmount = calculateDiscountFromCheapest(eligibleItems, itemsToDiscount);
        if(discountAmount > 0) {
            transactionItems.push({
                price: -discountAmount, unitPrice: -discountAmount, quantity: 1,
                category_id: categoryId, category_type: 'buy_x_get_x_minus_1',
                categoryName: `${categoryName} (買${totalQuantity}送${itemsToDiscount})`, originalName: categoryName, rules: rules,
                displayText: `-${discountAmount}`
            });
        }
        const subText = `已套用「${categoryName}」優惠`;
        updateReceipt();
        updateDisplay(subText);
    }

    function applyProgressivePairDiscount(categoryId, categoryName, rules) {
        const { target_category_id } = rules;
        const eligibleItems = transactionItems.filter(item => {
            if (target_category_id == 0) return item.price > 0 && item.category_type === 'product';
            return item.category_id == target_category_id && item.price > 0;
        });
        const totalQuantity = eligibleItems.reduce((sum, item) => sum + item.quantity, 0);
        transactionItems = transactionItems.filter(item => item.category_id !== categoryId);
        if (totalQuantity === 0) { 
            const subText = `不符合「${categoryName}」活動資格`;
            updateDisplay(subText);
            updateReceipt(subText);
            return;
        }
        let effectiveQuantity = totalQuantity;
        let subText = `已套用「${categoryName}」優惠`;
        let promptText = null;
        if (totalQuantity % 2 === 0 && totalQuantity > 0) {
            effectiveQuantity = totalQuantity - 1;
            const targetItemName = eligibleItems.length > 0 ? `「${eligibleItems[0].categoryName}」`:"";
            promptText = `提示: 再加購 1 件${targetItemName}可享更多優惠！`;
            subText = promptText;
        }
        if (effectiveQuantity < 1) {
            updateReceipt(promptText);
            updateDisplay(subText);
            return;
        }
        const paidCount = Math.ceil(effectiveQuantity / 2);
        const freeCount = Math.floor(effectiveQuantity / 2);
        const discountAmount = calculateDiscountFromCheapest(eligibleItems, freeCount);
        if (discountAmount > 0) {
            transactionItems.push({
                price: -discountAmount, unitPrice: -discountAmount, quantity: 1,
                category_id: categoryId, category_type: 'buy_odd_even',
                categoryName: `${categoryName} (買${paidCount}送${freeCount})`, originalName: categoryName, rules: rules,
                displayText: `-${discountAmount}`
            });
        }
        updateReceipt(promptText);
        updateDisplay(subText);
    }

    function calculateDiscountFromCheapest(items, count) {
        const allIndividualItems = [];
        items.forEach(item => {
            for (let i = 0; i < item.quantity; i++) {
                allIndividualItems.push({ unitPrice: item.unitPrice });
            }
        });
        allIndividualItems.sort((a, b) => a.unitPrice - b.unitPrice);
        return allIndividualItems.slice(0, count).reduce((sum, item) => sum + item.unitPrice, 0);
    }
    
    // =================================================================
    // SECTION 4: 結帳與收據
    // =================================================================

    function enterPaymentMode() {
        finalTotalForPayment = calculateCurrentTotal();
        inPaymentMode = true;
        isReadyForNewInput = true;
        expression = [];
        currentInput = '0';
        
        categoryButtons.forEach(btn => {
            if (btn.dataset.type === 'discount_percent') {
                btn.disabled = false;
            } else {
                btn.disabled = true;
            }
        });
        updateDisplay();
    }

    function enterFinalPaymentStage() {
        finalTotalForPayment = calculateCurrentTotal();
        equalsBtn.style.display = 'none';
        checkoutBtn.style.display = 'block';
        categoryButtons.forEach(btn => btn.disabled = true);
        updateDisplay();
    }
    
    async function handleCheckout(paidAmount = null) {
    const amountPaid = paidAmount ?? parseFloat(currentInput);
    if (isNaN(amountPaid) || amountPaid < finalTotalForPayment) {
        return updateDisplay(`金額不足，應收: ${finalTotalForPayment.toLocaleString('en-US')}`);
    }

    // --- ↓↓↓ 修正點：在這裡呼叫 sendTransactionToServer 時傳入 paidAmount 和 change ↓↓↓ ---
    const change = amountPaid - finalTotalForPayment;
    await sendTransactionToServer(amountPaid, change);
    // --- ↑↑↑ 修正結束 ↑↑↑ ---

    currentInput = amountPaid.toString();
    updateDisplay(`找零: ${change.toLocaleString('en-US')}`);
    updateReceiptForCheckout(amountPaid, finalTotalForPayment);

    isTransactionComplete = true;
}
    
    function updateReceipt(promptText = null) {
        receiptDetails.className = '';
        if (transactionItems.length === 0 && !promptText) {
            receiptDetails.className = 'd-flex justify-content-center align-items-center h-100';
            receiptDetails.innerHTML = '<span class="text-muted">暫無商品</span>';
            return;
        }
        
        let headerHtml = `
            <div class="receipt-line receipt-header">
                <div class="flex-grow-1">商品</div>
                <div style="width: 50px;" class="text-center">數量</div>
                <div style="width: 70px;" class="text-end">單價</div>
                <div style="width: 80px;" class="text-end">金額</div>
            </div>`;

        let itemsHtml = transactionItems.map(item => {
            const isProduct = item.category_type === 'product' && item.quantity > 0;
            return `
                <div class="receipt-line ${item.price < 0 ? 'text-danger' : ''}">
                    <div class="flex-grow-1">${item.categoryName}</div>
                    ${isProduct ? `
                        <div style="width: 50px;" class="text-center">${item.quantity}</div>
                        <div style="width: 70px;" class="text-end">${item.unitPrice.toLocaleString()}</div>
                    ` : `
                        <div style="width: 120px;"></div>
                    `}
                    <div style="width: 80px;" class="text-end fw-bold">${item.price.toLocaleString()}</div>
                </div>`;
        }).join('');

        let promptHtml = '';
        if (promptText) {
            promptHtml = `<div class="receipt-prompt">${promptText}</div>`;
        }
        
        receiptDetails.innerHTML = `<div>${headerHtml}<div class="item-list">${itemsHtml}</div></div>${promptHtml}`;
        receiptDetails.scrollTop = receiptDetails.scrollHeight;
    }
    
    function updateReceiptForCheckout(amountPaid, transactionTotal) {
        receiptDetails.className = 'd-flex flex-column h-100';
        
        const positiveItemsTotal = transactionItems.filter(item => item.price > 0).reduce((sum, item) => sum + item.price, 0);
        const allDiscounts = transactionItems.filter(item => item.price < 0);
        
        const discountHtml = allDiscounts.map(slot =>
            `<div class="receipt-line">
                <span>${slot.categoryName}</span>
                <span class="text-danger">${slot.price.toLocaleString()}</span>
            </div>`
        ).join('');

        receiptDetails.innerHTML = `
            <div>
                <div class="receipt-line">
                    <span>商品總計</span>
                    <span class="fw-bold">${positiveItemsTotal.toLocaleString()}</span>
                </div>
            </div>
            <div class="flex-grow-1"></div>
            <div class="pt-2">
                ${discountHtml}
                <hr class="my-1">
                <div class="receipt-line fw-bold">
                    <span>應收金額</span>
                    <span>${transactionTotal.toLocaleString()}</span>
                </div>
                <div class="receipt-line">
                    <span>實收現金</span>
                    <span>${amountPaid.toLocaleString()}</span>
                </div>
                <div class="receipt-line">
                    <span>找零</span>
                    <span>${(amountPaid - transactionTotal).toLocaleString()}</span>
                </div>
            </div>`;
    }
    
    // =================================================================
    // SECTION 5: 伺服器通訊
    // =================================================================
    async function sendTransactionToServer(paidAmount, changeReceived) {
    const expandedItems = [];
    transactionItems.forEach(item => {
        for (let i = 0; i < item.quantity; i++) {
            expandedItems.push({ price: item.unitPrice, category_id: item.category_id, category_type: item.category_type });
        }
    });
    try {
        const response = await fetch("/cashier/record_transaction", {
            method: "POST", headers: { "Content-Type": "application/json" },
            // --- ↓↓↓ 修正點：在 body 中新增 cash_received 和 change_given ↓↓↓ ---
            body: JSON.stringify({ 
                location_slug: POS_LOCATION_SLUG, 
                items: expandedItems,
                cash_received: paidAmount, // 新增
                change_given: changeReceived // 新增
            }),
            // --- ↑↑↑ 修正結束 ↑↑↑ ---
        });
        if (!response.ok) throw new Error("網路回應不正確");
        const result = await response.json();
        if (result.success) {
            document.getElementById("total-sales").innerText = `$ ${Math.round(result.total_sales).toLocaleString()}`;
            document.getElementById("total-transactions").innerText = result.total_transactions;
            document.getElementById("total-items").innerText = result.total_items;
        } else { updateDisplay(`傳送失敗: ${result.error}`); }
    } catch (error) { console.error("結帳時發生錯誤:", error); updateDisplay("傳送失敗"); }
}
    
    async function sendOtherIncomeToServer(amount, type) {
        try {
            const response = await fetch("/cashier/record_other_income", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ location_slug: POS_LOCATION_SLUG, amount, type }),
            });
            if (!response.ok) throw new Error("網路回應不正確");
            const result = await response.json();
            if (result.success) {
                document.getElementById("donation-total").innerText = `$ ${Math.round(result.donation_total).toLocaleString()}`;
                document.getElementById("other-total").innerText = `$ ${Math.round(result.other_total).toLocaleString()}`;
                const totalOtherIncome = (result.donation_total || 0) + (result.other_total || 0);
                document.getElementById("other-income-total").innerText = `$ ${Math.round(totalOtherIncome).toLocaleString()}`;
            }
        } catch (error) { console.error("記錄其他收入時發生錯誤:", error); }
    }

    async function handleOtherIncome(type) {
        if (checkAndResetAfterTransaction()) return;
        const value = safeCalculate([...expression, currentInput].join(' '));
        if (value <= 0) return;
        await sendOtherIncomeToServer(value, type);
        const typeText = type === 'donation' ? '愛心捐款' : '其他收入';
        updateReceiptForOtherIncome(value, typeText);
        updateDisplay(`${typeText} ${value.toLocaleString()} 已記錄`);
        isTransactionComplete = true;
    }

    function updateReceiptForOtherIncome(amount, title) {
        receiptDetails.className = 'd-flex justify-content-center align-items-center h-100';
        receiptDetails.innerHTML = `
            <div class="text-center p-3">
                <h4 class="fw-bold mb-2">${title}</h4>
                <p class="text-muted small mb-3">您的每一份支持，都是改變的力量</p>
                <hr class="my-2">
                <div class="d-flex justify-content-center align-items-center fs-4 mt-3 px-3">
                    <span class="text-success fw-bold me-2">NT$</span>
                    <span class="fw-bold">${amount.toLocaleString()}</span>
                </div>
            </div>`;
    }
    
    // =================================================================
    // SECTION 6: 初始化與事件綁定
    // =================================================================

    document.querySelectorAll(".number-btn").forEach(btn => btn.addEventListener('click', () => handleNumber(btn.dataset.value)));
    document.querySelectorAll(".operator-btn").forEach(btn => btn.addEventListener('click', () => handleOperator(btn.dataset.value)));
    
    document.querySelector('[data-action="clear"]').addEventListener('click', resetCalculator);
    document.querySelector('[data-action="undo"]').addEventListener('click', handleUndo);
    document.querySelector('[data-action="backspace"]').addEventListener('click', () => {
        if (currentInput.length > 1) currentInput = currentInput.slice(0, -1);
        else currentInput = '0';
        updateDisplay();
    });

    categoryButtons.forEach(btn => btn.addEventListener('click', () => handleCategoryClick(btn)));
    equalsBtn.addEventListener('click', handleEquals);
    checkoutBtn.addEventListener('click', () => handleCheckout());

    if (donationBtn) donationBtn.addEventListener('click', () => handleOtherIncome('donation'));
    if (otherIncomeBtn) otherIncomeBtn.addEventListener('click', () => handleOtherIncome('other'));

    resetCalculator();
});