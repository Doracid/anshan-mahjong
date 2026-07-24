# 鞍山麻将 (Anshan Mahjong)

基于 Python + Pygame 的鞍山麻将，支持本地单机对战和联网多人对战。

## 玩法简介

鞍山麻将的规则包括：
- 4人游戏，万/饼/条/风/箭牌
- 有混牌（万能牌），根据骰子确定
- 支持碰、杠（明杠/暗杠/补杠/旋风杠）、吃、胡
- 支持点炮、自摸、流局

## 运行方式

### 环境要求
- Python 3.12+
- 安装依赖：`pip install pygame websockets`

### 单机模式
```bash
python main.py
```
选择"单机模式"，你和3个AI对手对战。

### 联网对战

1. **启动服务器**（部署在公网或本地）：
```bash
python server/server.py --port 8765
```

2. **玩家1启动客户端**，选择"联网对战"，填入服务器地址，创建房间：
```bash
python main.py
```

3. **玩家2启动客户端**，连接同一服务器，输入玩家1的房间号加入。

4. 双方准备后自动开始，空缺位置由AI补位。

## 项目结构

```
├── main.py                   # Pygame 客户端（单机 + 联网）
├── game/
│   ├── entities.py           # Tile, Player 等实体类
│   ├── state.py              # GameState 状态机
│   ├── logic.py              # 规则逻辑（胡牌判定等）
│   ├── cpu_player.py         # AI 决策
│   ├── network.py            # WebSocket 客户端网络层
│   └── config.py             # 配置常量
├── server/
│   ├── server.py             # WebSocket 服务器
│   ├── room.py               # 房间管理 + AI 补位
│   └── protocol.py           # 消息协议定义
└── picture/
    └── pai/                  # 牌面图片资源
```

## 技术栈

- **客户端**：Python Pygame（UI渲染 + 事件循环）
- **服务器**：Python asyncio + websockets
- **通信**：WebSocket JSON 消息
- **AI**：内置 CPU 玩家，基于规则决策

## 联网协议

客户端和服务器通过 JSON 消息通信，详见 `server/protocol.py`。
