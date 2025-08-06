document.addEventListener('DOMContentLoaded', function () {
    // 獲取所有顯示區的元素
    const displayExpression1 = document.getElementById('display-expression-1');
    const displayExpression2 = document.getElementById('display-expression-2');
    const displayInput = document.getElementById('display-input');
    const displayPreview = document.getElementById('display-preview');
    const calcButtons = document.querySelectorAll('.calc-btn');
    const equalsBtn = document.getElementById('equals-btn');

    let state = {
        currentInput: '0',
        expression: '',
        lastInputIsOperator: false,
    };

    // --- 核心函式：更新顯示 ---
    function updateDisplay() {
        // 增加單行的最大長度，讓第一行可以容納更多字元
        const MAX_LINE_LENGTH = 25; 

        let line1 = '';
        let line2 = '';

        if (state.expression.length > MAX_LINE_LENGTH) {
            let splitIndex = -1;
            // 從後面開始往前找，找到一個最接近但不超過最大長度的分割點
            for (let i = state.expression.length - 1; i >= 0; i--) {
                if ("+-*/".includes(state.expression[i])) {
                    // 如果前半段的長度是我們想要的，就用這個分割點
                    if (state.expression.substring(0, i + 1).length <= MAX_LINE_LENGTH) {
                        splitIndex = i;
                        break;
                    }
                }
            }
            
            if (splitIndex !== -1) {
                // 如果找到合適的分割點
                line1 = state.expression.substring(0, splitIndex + 1);
                line2 = state.expression.substring(splitIndex + 1);
            } else {
                // 如果找不到（例如一個超長的數字），則不分割，讓其在第一行滾動
                line1 = state.expression;
                line2 = '';
            }

        } else {
            // 如果算式不長，就只顯示在第一行
            line1 = state.expression;
            line2 = '';
        }

        displayExpression1.innerText = line1;
        displayExpression2.innerText = line2;

        displayInput.innerText = state.currentInput;

        // 即時預覽結果 (邏輯不變)
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

    // --- 其他處理函式 (與上次相同，無需修改) ---
    function handleNumber(value) {
        if (state.currentInput === '0' && value !== '.') {
            state.currentInput = value;
        } else {
            if (value === '.' && state.currentInput.includes('.')) return;
            state.currentInput += value;
        }
        state.lastInputIsOperator = false;
        updateDisplay();
    }

    function handleOperator(value) {
        if (state.lastInputIsOperator) {
            state.expression = state.expression.slice(0, -1) + value;
        } else {
            state.expression += state.currentInput + value;
            state.currentInput = '0';
        }
        state.lastInputIsOperator = true;
        updateDisplay();
    }

    function handleAction(action) {
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

            sendTransaction(total, finalExpression);
        } catch (e) {
            displayInput.innerText = '錯誤';
            setTimeout(() => handleAction('clear'), 1500);
        }
    }

    async function sendTransaction(total, expression) {
        // AJAX 邏輯不變
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

    // --- 事件監聽 (邏輯不變) ---
    calcButtons.forEach(button => {
        button.addEventListener('click', () => {
            const value = button.dataset.value;
            const action = button.dataset.action;
            if (value) {
                (value >= '0' && value <= '9') || value === '.' ? handleNumber(value) : handleOperator(value);
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

    updateDisplay(); // 初始顯示
});