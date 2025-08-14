document.addEventListener("DOMContentLoaded", function () {
    // --- DOM 元素 ---
    const displayExpression = document.getElementById("display-expression");
    const displayMain = document.getElementById("display-main");
    const displaySub = document.getElementById("display-sub");
    const receiptDetails = document.getElementById("receipt-details");
    
    const calcButtons = document.querySelectorAll(".calc-btn");
    const equalsBtn = document.getElementById("equals-btn");
    const donationBtn = document.getElementById("donation-btn");

    // --- 狀態常量 ---
    const STATE = {
        INPUTTING_ITEMS: 'inputting_items',      // 狀態一：輸入中
        AWAITING_PAYMENT: 'awaiting_payment',    // 狀態二：等待收款
        DISPLAYING_CHANGE: 'displaying_change',  // 狀態三：顯示找零 (交易結束)
        DONATION_COMPLETE: 'donation_complete'   // 狀態四：顯示捐款 (捐款結束)
    };

    // --- 狀態變數 ---
    let currentState = STATE.INPUTTING_ITEMS;
    let expression = [];
    let currentInput = '0';
    let transactionTotal = 0;
    let equalsTimeout = null;
    const DOUBLE_PRESS_THRESHOLD = 400;

    // --- 核心功能函式 ---

    function updateDisplay() {
        displayExpression.innerText = expression.join(' ');
        displayExpression.scrollLeft = displayExpression.scrollWidth;
        displayMain.innerText = parseFloat(currentInput).toLocaleString();

        switch (currentState) {
            case STATE.INPUTTING_ITEMS:
                const containsOperator = expression.some(item => ['+', '-', '*', '/'].includes(item));
                const isPositiveNumber = parseFloat(currentInput) > 0;
                displaySub.innerText = '請輸入商品價格、折扣或捐款金額';
                donationBtn.disabled = containsOperator || !isPositiveNumber;
                equalsBtn.disabled = currentInput === '0' && expression.length === 0;
                break;
            case STATE.AWAITING_PAYMENT:
                displaySub.innerText = `應收: ${transactionTotal.toLocaleString()} / 請輸入收款金額`;
                donationBtn.disabled = false;
                const amountPaidCheck = parseFloat(currentInput);
                equalsBtn.disabled = isNaN(amountPaidCheck) || amountPaidCheck < transactionTotal;
                break;
            case STATE.DISPLAYING_CHANGE:
                const amountPaid = parseFloat(currentInput);
                const change = amountPaid - transactionTotal;
                displaySub.innerText = `找零: ${change.toLocaleString()} (收到 ${amountPaid.toLocaleString()})`;
                donationBtn.disabled = true;
                equalsBtn.disabled = true;
                break;
            case STATE.DONATION_COMPLETE:
                displaySub.innerText = '感謝您的愛心捐款！';
                donationBtn.disabled = true;
                equalsBtn.disabled = true;
                break;
        }
    }

    function resetCalculator() {
        expression = [];
        currentInput = '0';
        transactionTotal = 0;
        currentState = STATE.INPUTTING_ITEMS;
        if(receiptDetails) receiptDetails.innerHTML = '<div class="flex-grow-1 d-flex align-items-center justify-content-center"><p class="text-muted m-0">暫無交易</p></div>';
        clearTimeout(equalsTimeout);
        equalsTimeout = null;
        updateDisplay();
    }
    
    function clearEntry() {
        if ([STATE.DISPLAYING_CHANGE, STATE.DONATION_COMPLETE].includes(currentState)) {
            resetCalculator();
        } else {
            currentInput = '0';
        }
        updateDisplay();
    }

    function handleNumber(value) {
        if ([STATE.DISPLAYING_CHANGE, STATE.DONATION_COMPLETE].includes(currentState)) {
            resetCalculator();
        }
        if (currentInput === '0' && value !== '.') {
            currentInput = value;
        } else {
            if (value === '.' && currentInput.includes('.')) return;
            if (currentInput.length > 15) return;
            currentInput += value;
        }
        updateDisplay();
    }

    function handleOperator(op) {
        if ([STATE.DISPLAYING_CHANGE, STATE.DONATION_COMPLETE].includes(currentState)) {
            resetCalculator();
        }
        if (currentState !== STATE.INPUTTING_ITEMS) return;
        
        if (currentInput === '0' && expression.length > 0 && ['+', '-', '*', '/'].includes(expression[expression.length - 1])) {
            expression[expression.length - 1] = op;
        } else {
            expression.push(currentInput);
            expression.push(op);
            currentInput = '0';
        }
        updateDisplay();
    }

    function handleBackspace() {
        if ([STATE.DISPLAYING_CHANGE, STATE.DONATION_COMPLETE].includes(currentState)) {
            resetCalculator();
            return;
        }
        if (currentInput.length > 1) {
            currentInput = currentInput.slice(0, -1);
        } else if (currentInput !== '0') {
            currentInput = '0';
        } else if (expression.length > 0) {
            expression.pop(); 
            currentInput = expression.pop() || '0';
        }
        updateDisplay();
    }

    function handleEquals() {
        if (equalsBtn.disabled) return;
        if (currentState === STATE.INPUTTING_ITEMS) {
            if (expression.length === 0 && currentInput === '0') return;
            
            expression.push(currentInput);
            
            if (['+', '-', '*', '/'].includes(expression[expression.length - 1])) {
                expression.pop();
            }

            try {
                transactionTotal = safeCalculate(expression.join(''));
                currentState = STATE.AWAITING_PAYMENT;
                currentInput = '0';
            } catch (e) {
                displaySub.innerText = "計算錯誤";
                setTimeout(resetCalculator, 1500);
            }
        } else if (currentState === STATE.AWAITING_PAYMENT) {
            const amountPaid = parseFloat(currentInput);
            if (isNaN(amountPaid) || amountPaid < transactionTotal) {
                displaySub.innerText = "收款金額不足！";
                return;
            }
            currentState = STATE.DISPLAYING_CHANGE;
            sendTransaction(amountPaid);
        }
        updateDisplay();
    }

    function handleDonation() {
        if (donationBtn.disabled) return;

        if (currentState === STATE.INPUTTING_ITEMS) {
            const donationAmount = parseFloat(currentInput);
            if (isNaN(donationAmount) || donationAmount <= 0) {
                displaySub.innerText = "請輸入有效捐款金額";
                return;
            }
            sendDonation(donationAmount);
            updateReceipt('donation', { amount: donationAmount });
            currentState = STATE.DONATION_COMPLETE;

        } else if (currentState === STATE.AWAITING_PAYMENT) {
            const amountPaid = parseFloat(currentInput);
            const finalAmountPaid = (currentInput === '0' || isNaN(amountPaid)) ? transactionTotal : amountPaid;
            if (finalAmountPaid < transactionTotal) {
                displaySub.innerText = "收款金額不足！";
                return;
            }
            sendDonation(transactionTotal);
            currentInput = finalAmountPaid.toString();
            currentState = STATE.DISPLAYING_CHANGE;
            updateReceipt('donation_with_change', { 
                amount: transactionTotal,
                paid: finalAmountPaid,
                change: finalAmountPaid - transactionTotal
            });
        }
        updateDisplay();
    }

    function safeCalculate(expr) {
        let sanitizedExpr = expr.replace(/[^0-9.+\-*/]/g, '').replace(/×/g, "*").replace(/÷/g, "/");
        if (['+', '-', '*', '/'].includes(sanitizedExpr.slice(-1))) {
            sanitizedExpr = sanitizedExpr.slice(0, -1);
        }
        if (sanitizedExpr.trim() === '') return 0;
        return new Function('return ' + sanitizedExpr)();
    }

    // --- 後端通訊 (保留原樣) ---
    async function sendTransaction(amountPaid) {
        if (typeof POS_LOCATION_SLUG === 'undefined') return;
        const fullExpressionStr = expression.join('');
        const parts = fullExpressionStr.split('-');
        const saleItemsExpression = parts[0];
        const discounts = parts.slice(1).map(d => parseFloat(d)).filter(d => !isNaN(d) && d > 0);
        const items = saleItemsExpression.split(/[\+\*\/]/).filter(i => i !== '' && parseFloat(i) > 0);
        try {
            const response = await fetch("/cashier/record_transaction", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ location_slug: POS_LOCATION_SLUG, total: transactionTotal, items: items.length, discounts: discounts }),
            });
            if (!response.ok) throw new Error("網路回應不正確");
            const result = await response.json();
            if (result.success) {
                updateSidebar(result);
                updateReceipt('transaction', { itemTotal: transactionTotal + discounts.reduce((a, b) => a + b, 0), discounts: discounts, finalTotal: transactionTotal, paid: amountPaid, change: amountPaid - transactionTotal });
            }
        } catch (error) { console.error("記錄交易時發生錯誤:", error); displaySub.innerText = "傳送失敗"; }
    }
    async function sendDonation(amount) {
        if (typeof POS_LOCATION_SLUG === 'undefined') return;
        try {
            const response = await fetch("/cashier/record_donation", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ location_slug: POS_LOCATION_SLUG, amount: amount }),
            });
            if (!response.ok) throw new Error("網路回應不正確");
            const result = await response.json();
            if (result.success && document.getElementById("other-income")) {
                document.getElementById("other-income").innerText = `$ ${Math.round(result.other_income).toLocaleString()}`;
            }
        } catch (error) { console.error("記錄捐款時發生錯誤:", error); alert("記錄捐款失敗。"); }
    }
    function updateSidebar(data) {
        if (document.getElementById("total-sales")) {
            document.getElementById("total-sales").innerText = `$ ${Math.round(data.total_sales).toLocaleString()}`;
            document.getElementById("total-transactions").innerText = data.total_transactions;
            document.getElementById("total-items").innerText = data.total_items;
        }
    }

    /**
     * 修正點：統一捐款收據的顯示格式，使其符合截圖樣式
     */
    function updateReceipt(type, data) {
        if (!receiptDetails) return;
        receiptDetails.innerHTML = ''; 

        if (type === 'transaction') {
            let discountHtml = '<div style="height: 1.5rem;"></div>';
            if (data.discounts && data.discounts.length > 0) { discountHtml = data.discounts.map(d => `<div class="d-flex justify-content-between"><span>折扣券</span><span>-${d.toLocaleString()}</span></div>`).join(''); }
            receiptDetails.innerHTML = `<div><div class="d-flex justify-content-between"><span>商品總計</span><span>${(data.itemTotal || 0).toLocaleString()}</span></div>${discountHtml}</div><hr class="my-1"><div class="flex-grow-1"></div><div><div class="d-flex justify-content-between fw-bold"><span>應收金額</span><span>${(data.finalTotal || 0).toLocaleString()}</span></div><div class="d-flex justify-content-between"><span>實收現金</span><span>${(data.paid || 0).toLocaleString()}</span></div><div class="d-flex justify-content-between"><span>找零</span><span>${(data.change || 0).toLocaleString()}</span></div></div>`;
        } 
        // 針對所有捐款類型，使用統一的顯示格式
        else if (type === 'donation' || type === 'donation_with_change') {
            const donationAmount = data.amount || 0;
            
            receiptDetails.innerHTML = `
                <div class="text-center pt-3 pb-2">
                    <h4 class="fw-bold mb-2">愛心捐款</h4>
                    <p class="text-muted small mb-3">您的每一份支持，都是改變的力量</p>
                    <hr class="my-2">
                    <div class="d-flex justify-content-between align-items-center fs-4 mt-3">
                        <span class="text-success fw-bold">NT$</span>
                        <span class="fw-bold">${donationAmount.toLocaleString()}</span>
                    </div>
                </div>
            `;
        }
    }

    // --- 事件監聽 ---
    calcButtons.forEach(button => {
        button.addEventListener("click", () => {
            const value = button.dataset.value;
            const action = button.dataset.action;
            if (value) { if (['+', '-', '*', '/'].includes(value)) handleOperator(value); else handleNumber(value); } 
            else if (action) { if (action === 'clear') resetCalculator(); if (action === 'clearEntry') clearEntry(); if (action === 'backspace') handleBackspace(); }
        });
    });
    equalsBtn.addEventListener("click", handleEquals);
    donationBtn.addEventListener("click", handleDonation);

    // --- 鍵盤支援 ---
    document.addEventListener("keydown", (event) => {
        const key = event.key;
        if (event.target === displayMain && !/^[0-9.]$/.test(key) && key.length === 1) { event.preventDefault(); }
        if ((key >= '0' && key <= '9') || key === '.') handleNumber(key);
        if (key === 'Enter' || key === '=') {
            event.preventDefault();
            if (equalsTimeout) { clearTimeout(equalsTimeout); equalsTimeout = null; handleDonation(); } 
            else { equalsTimeout = setTimeout(() => { handleEquals(); equalsTimeout = null; }, DOUBLE_PRESS_THRESHOLD); }
        }
        if (['+', '-', '*', '/'].includes(key)) handleOperator(key);
        if (key === 'Backspace') handleBackspace();
        if (key.toLowerCase() === 'c' || key === 'Escape') resetCalculator();
    });

    resetCalculator();
});
