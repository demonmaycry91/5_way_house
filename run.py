from my_app import create_app

app = create_app()

if __name__ == '__main__':
    # 新增 host='0.0.0.0' 以允許外部連線
    app.run(host='0.0.0.0', debug=True)