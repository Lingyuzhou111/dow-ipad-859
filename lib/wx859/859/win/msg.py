import websocket

def on_message(ws, message):
    """当接收到消息时打印消息"""
    print(f"收到消息: {message}")

def on_error(ws, error):
    """当发生错误时打印错误"""
    print(f"发生错误: {error}")

def on_close(ws, close_status_code, close_msg):
    """当连接关闭时打印提示"""
    print("### 连接已关闭 ###")

def on_open(ws):
    """当连接建立时打印提示"""
    print("连接已建立...")

if __name__ == "__main__":
    # 将此URL替换为你的WebSocket服务器地址
    ws_url = "ws://127.0.0.1:8059/ws/你的wxid"
    
    # 创建一个WebSocketApp实例
    ws = websocket.WebSocketApp(ws_url,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)

    # 运行WebSocket客户端，它会一直运行直到连接关闭
    ws.run_forever()