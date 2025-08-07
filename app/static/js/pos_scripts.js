document.addEventListener('DOMContentLoaded', function () {
    // 獲取所有需要的 DOM 元素 (已移除聲音相關元素)
    const displayExpression1 = document.getElementById('display-expression-1');
    const displayExpression2 = document.getElementById('display-expression-2');
    const displayInput = document.getElementById('display-input');
    const displayPreview = document.getElementById('display-preview');
    const calcButtons = document.querySelectorAll('.calc-btn');
    const equalsBtn = document.getElementById('equals-btn');

    // 狀態物件 (已移除聲音相關狀態)
    let state = {
        currentInput: '0',
        expression: '',
        lastInputIsOperator: false,
        isTransactionComplete: false,
    };

    // --- 更新顯示 ---
    function updateDisplay() {
        const MAX_LINE_LENGTH = 25; 
        let line1 = '', line2 = '';
        if (state.expression.length > MAX_LINE_LENGTH) {
            let splitIndex = -1;
            for (let i = state.expression.length - 1; i >= 0; i--) {
                if ("+-*/".includes(state.expression[i])) {
                    if (state.expression.substring(0, i + 1).length <= MAX_LINE_LENGTH) {
                        splitIndex = i;
                        break;
                    }
                }
            }
            if (splitIndex !== -1) {
                line1 = state.expression.substring(0, splitIndex + 1);
                line2 = state.expression.substring(splitIndex + 1);
            } else {
                line1 = state.expression;
            }
        } else {
            line1 = state.expression;
        }
        displayExpression1.innerText = line1;
        displayExpression2.innerText = line2;
        displayInput.innerText = parseFloat(state.currentInput).toLocaleString();

        try {
            const previewExpr = (state.expression + state.currentInput).replace(/[+\-*/]$/, '');
            if (previewExpr) {
                const previewResult = eval(previewExpr.replace(/×/g, '*').replace(/÷/g, '/'));
                displayPreview.innerText = '= ' + previewResult.toLocaleString();
            } else {
                displayPreview.innerText = '';
            }
        } catch (e) {
            displayPreview.innerText = '';
        }
    }
    
    // --- 輸入處理 ---
    function handleNumber(value) {
        if (state.isTransactionComplete) {
            handleAction('clear');
        }
        if (value === '00') {
            if (state.currentInput !== '0') state.currentInput += '00';
        } else {
            if (state.currentInput === '0' && value !== '.') {
                state.currentInput = value;
            } else {
                if (value === '.' && state.currentInput.includes('.')) return;
                state.currentInput += value;
            }
        }
        state.lastInputIsOperator = false;
        updateDisplay();
    }

    function handleOperator(value) {
        state.isTransactionComplete = false;
        if (state.lastInputIsOperator) {
            state.expression = state.expression.slice(0, -1) + value;
        } else {
            state.expression += state.currentInput + value;
            state.currentInput = '0';
        }
        state.lastInputIsOperator = true;
        updateDisplay();
    }
    
    // --- 功能鍵處理 ---
    function handleAction(action) {
        if(action !== 'equals') state.isTransactionComplete = false;
        switch (action) {
            case 'clear':
                state.currentInput = '0';
                state.expression = '';
                state.lastInputIsOperator = false;
                break;
            case 'clearEntry':
                state.currentInput = '0';
                break;
            case 'backspace':
                if (state.currentInput.length > 1) {
                    state.currentInput = state.currentInput.slice(0, -1);
                } else {
                    state.currentInput = '0';
                }
                break;
            case 'equals':
                handleEquals();
                return;
        }
        updateDisplay();
    }
    
    function handleEquals() {
        if (state.lastInputIsOperator) return;
        const finalExpression = state.expression + state.currentInput;
        try {
            const total = eval(finalExpression.replace(/×/g, '*').replace(/÷/g, '/'));
            if (isNaN(total)) throw new Error("無效計算");
            
            displayExpression1.innerText = '';
            displayExpression2.innerText = finalExpression + ' =';
            displayInput.innerText = total.toLocaleString();
            displayPreview.innerText = '';
            
            state.expression = '';
            state.currentInput = total.toString();
            state.lastInputIsOperator = false;
            state.isTransactionComplete = true;

            sendTransaction(total, finalExpression);
        } catch (e) {
            displayInput.innerText = '錯誤';
            setTimeout(() => handleAction('clear'), 1500);
        }
    }

    // --- 後端通訊 ---
    async function sendTransaction(total, expression) {
        try {
            const response = await fetch('/cashier/record_transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    location: POS_LOCATION,
                    total: total,
                    items: expression.split(/[+\-*/]/).length,
                }),
            });
            if (!response.ok) throw new Error('網路回應不正確');
            
            const result = await response.json();
            if (result.success) {
                document.getElementById('total-sales').innerText = `$ ${Math.round(result.total_sales).toLocaleString()}`;
                document.getElementById('total-items').innerText = result.total_items;
                document.getElementById('total-transactions').innerText = result.total_transactions;
            } else {
                 displayInput.innerText = `後端錯誤`;
            }
        } catch (error) {
            console.error('記錄交易時發生錯誤:', error);
            displayInput.innerText = '傳送失敗';
        }
    }

    // --- 事件監聽 ---
    calcButtons.forEach(button => {
        button.addEventListener('click', () => {
            const value = button.dataset.value;
            const action = button.dataset.action;
            if (value) {
                (value.includes('0') || (value > '0' && value <= '9') || value === '.') ? handleNumber(value) : handleOperator(value);
            } else if (action) {
                handleAction(action);
            }
        });
    });
    equalsBtn.addEventListener('click', handleEquals);

    document.addEventListener('keydown', (event) => {
        const key = event.key;
        if (key >= '0' && key <= '9' || key === '.') handleNumber(key);
        else if (['+', '-', '*', '/'].includes(key)) handleOperator(key === '*' ? '×' : key === '/' ? '÷' : key);
        else if (key === 'Enter' || key === '=') { event.preventDefault(); handleEquals(); }
        else if (key === 'Backspace') handleAction('backspace');
        else if (key.toLowerCase() === 'c' || key === 'Escape') handleAction('clear');
    });

    updateDisplay();
});