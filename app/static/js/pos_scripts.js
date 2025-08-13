document.addEventListener("DOMContentLoaded", function () {
    // 獲取所有需要的 DOM 元素
    const displayExpression1 = document.getElementById("display-expression-1");
    const displayExpression2 = document.getElementById("display-expression-2");
    const displayInput = document.getElementById("display-input");
    const displayPreview = document.getElementById("display-preview");
    const calcButtons = document.querySelectorAll(".calc-btn");
    const equalsBtn = document.getElementById("equals-btn");

    // 狀態物件
    let state = {
        currentInput: "0",
        expression: "",
        lastInputIsOperator: false,
        isTransactionComplete: false,
    };

    // --- 更新顯示 ---
    function updateDisplay() {
        const MAX_LINE_LENGTH = 25;
        let line1 = "",
            line2 = "";
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
            const previewExpr = (state.expression + state.currentInput).replace(
                /[+\-*/]$/,
                ""
            );
            if (previewExpr) {
                // *** 優化點：預覽也使用安全的計算函式 ***
                const previewResult = safeCalculate(previewExpr);
                displayPreview.innerText = "= " + previewResult.toLocaleString();
            } else {
                displayPreview.innerText = "";
            }
        } catch (e) {
            displayPreview.innerText = "";
        }
    }

    // --- 輸入處理 ---
    function handleNumber(value) {
        if (state.isTransactionComplete) {
            handleAction("clear");
        }
        if (value === "00") {
            if (state.currentInput !== "0") state.currentInput += "00";
        } else {
            if (state.currentInput === "0" && value !== ".") {
                state.currentInput = value;
            } else {
                if (value === "." && state.currentInput.includes(".")) return;
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
            state.currentInput = "0";
        }
        state.lastInputIsOperator = true;
        updateDisplay();
    }

    // --- 功能鍵處理 ---
    function handleAction(action) {
        if (action !== "equals") state.isTransactionComplete = false;
        switch (action) {
            case "clear":
                state.currentInput = "0";
                state.expression = "";
                state.lastInputIsOperator = false;
                break;
            case "clearEntry":
                state.currentInput = "0";
                break;
            case "backspace":
                if (state.currentInput.length > 1) {
                    state.currentInput = state.currentInput.slice(0, -1);
                } else {
                    state.currentInput = "0";
                }
                break;
            case "equals":
                handleEquals();
                return;
        }
        updateDisplay();
    }

    // *** 優化點：新增一個安全的計算函式來取代 eval() ***
    function safeCalculate(expression) {
        // 替換顯示用的運算符為 JS 可執行版本
        const executableExpression = expression.replace(/×/g, "*").replace(/÷/g, "/");
        
        // 使用正則表達式驗證表達式，只允許數字、小數點和基本運算符
        // 這可以防止任何非數學相關的程式碼被執行
        if (!/^[0-9.+\-*/\s]+$/.test(executableExpression)) {
            throw new Error("無效的運算式");
        }
        
        // 使用 Function 建構子，這是在受控環境下執行程式碼的較安全方式
        return new Function('return ' + executableExpression)();
    }

    function handleEquals() {
        if (state.lastInputIsOperator) return;
        const finalExpression = state.expression + state.currentInput;
        try {
            // *** 優化點：使用新的 safeCalculate 函式 ***
            const total = safeCalculate(finalExpression);
            if (isNaN(total)) throw new Error("無效計算");

            displayExpression1.innerText = "";
            displayExpression2.innerText = finalExpression + " =";
            displayInput.innerText = total.toLocaleString();
            displayPreview.innerText = "";

            state.expression = "";
            state.currentInput = total.toString();
            state.lastInputIsOperator = false;
            state.isTransactionComplete = true;

            sendTransaction(total, finalExpression);
        } catch (e) {
            console.error("計算錯誤:", e);
            displayInput.innerText = "錯誤";
            setTimeout(() => handleAction("clear"), 1500);
        }
    }

    // --- 後端通訊 ---
    async function sendTransaction(total, expression) {
        try {
            const response = await fetch("/cashier/record_transaction", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    // *** 修正點：將變數名稱從 POS_LOCATION_SLUG 改回 POS_LOCATION ***
                    // 這個變數是從 pos.html 樣板中傳入的
                    location_slug: POS_LOCATION, 
                    total: total,
                    items: expression.split(/[+\-*/]/).length,
                }),
            });
            if (!response.ok) throw new Error("網路回應不正確");

            const result = await response.json();
            if (result.success) {
                document.getElementById("total-sales").innerText = `$ ${Math.round(
                    result.total_sales
                ).toLocaleString()}`;
                document.getElementById("total-items").innerText = result.total_items;
                document.getElementById("total-transactions").innerText =
                    result.total_transactions;
            } else {
                displayInput.innerText = `後端錯誤`;
            }
        } catch (error) {
            console.error("記錄交易時發生錯誤:", error);
            displayInput.innerText = "傳送失敗";
        }
    }

    // --- 事件監聽 ---
    calcButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const value = button.dataset.value;
            const action = button.dataset.action;
            if (value) {
                // 檢查是否為數字或小數點
                if (!isNaN(parseFloat(value)) || value === '.') {
                    handleNumber(value);
                } else {
                    handleOperator(value);
                }
            } else if (action) {
                handleAction(action);
            }
        });
    });
    equalsBtn.addEventListener("click", handleEquals);

    document.addEventListener("keydown", (event) => {
        const key = event.key;
        if ((key >= "0" && key <= "9") || key === ".") handleNumber(key);
        else if (["+", "-", "*", "/"].includes(key))
            handleOperator(key === "*" ? "×" : key === "/" ? "÷" : key);
        else if (key === "Enter" || key === "=") {
            event.preventDefault();
            handleEquals();
        } else if (key === "Backspace") handleAction("backspace");
        else if (key.toLowerCase() === "c" || key === "Escape")
            handleAction("clear");
    });

    updateDisplay();
});
