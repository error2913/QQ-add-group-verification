from typing import Any, Dict, Tuple, TypedDict
import aiohttp
import asyncio
import json
import uuid
import random
from config import config
from data import Database
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# 定义验证信息的类型
class VerificationData(TypedDict):
    code: str  # 验证码
    task: asyncio.Task[None]  # 异步任务

# 全局状态存储
verification_pool: Dict[Tuple[int, int], VerificationData] = {}  # 验证池 {(user_id, group_id): data}
echo_map: Dict[str, asyncio.Future[Dict[str, Any]]] = {}  # API请求映射 {echo: future}
db = Database()

def generate_code() -> str:
    """生成6位随机数字验证码"""
    return ''.join(random.choices('0123456789', k=6))

async def call_api(
    ws: aiohttp.ClientWebSocketResponse,
    action: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """调用OneBot API"""
    echo = str(uuid.uuid4())
    future = asyncio.Future()
    echo_map[echo] = future
    
    try:
        await ws.send_str(json.dumps({
            "action": action,
            "params": params,
            "echo": echo
        }))
        return await future
    finally:
        echo_map.pop(echo, None)
        
async def send_group_msg(
    ws: aiohttp.ClientWebSocketResponse,
    group_id: int,
    message: str
):
    """发送群消息"""
    sleep_time = random.uniform(0.5, 1.5)  # 随机休眠时间
    await asyncio.sleep(sleep_time)
    
    logger.info(f"发送给群{group_id}的消息：{message}")
    
    await call_api(ws, "send_group_msg", {
        "group_id": group_id,
        "message": message 
    })
    

async def handle_group_increase(
    event: Dict[str, Any],
    ws: aiohttp.ClientWebSocketResponse
):
    """处理加群事件"""
    user_id = event["user_id"]
    group_id = event["group_id"]
    
    logger.info(f"用户{user_id}加入群{group_id}")
    
    white_list = await db.get_white_list()
    if group_id not in white_list:
        return  # 不在白名单群中不需要验证
    
    # 获取用户信息
    response = await call_api(ws, "get_stranger_info", {"user_id": user_id})
    if not response or response.get("retcode") != 0:
        logger.error(f"获取用户{user_id}信息失败")
        return
    
    qq_level = response["data"].get("qqLevel", 0)
    threshold = await db.get_threshold(group_id)
    if qq_level >= threshold:
        return  # 等级达标不需要验证

    # 生成并保存验证码
    verify_code = generate_code()
    key = (user_id, group_id)
    timeout = await db.get_timeout(group_id)
    verification_pool[key] = {
        "code": verify_code,
        "task": asyncio.create_task(kick_task(ws, user_id, group_id, timeout))
    }

    # 发送验证消息
    await send_group_msg(ws, group_id,
        f"[CQ:at,qq={user_id}] 欢迎加入！你当前的QQ等级为 {qq_level}，等级过低。请在时限发送验证码：{verify_code}（{timeout}秒内有效），否则将移出本群。")

async def kick_task(
    ws: aiohttp.ClientWebSocketResponse,
    user_id: int,
    group_id: int,
    timeout: int
):
    """超时踢出任务"""
    try:
        await asyncio.sleep(timeout)
        key = (user_id, group_id)
        if key in verification_pool:
            await call_api(ws, "set_group_kick", {
                "group_id": group_id,
                "user_id": user_id
            })
            del verification_pool[key]
            
        # 发送超时消息
        await send_group_msg(ws, group_id, f"{user_id} 验证超时，已自动移出本群。")
    except asyncio.CancelledError:
        pass  # 验证成功时任务会被取消

async def handle_group_msg(
    event: Dict[str, Any],
    ws: aiohttp.ClientWebSocketResponse
):
    """处理群消息"""
    user_id = event["user_id"]
    group_id = event["group_id"]
    
        # 兼容处理不同消息格式
    def extract_message_text(msg):
        """提取消息文本（兼容array/string格式）"""
        if isinstance(msg, str):
            return msg.strip()
        if isinstance(msg, list):
            return ''.join(
                seg["data"]["text"].strip()
                for seg in msg
                if seg["type"] == "text"
            )
        return ""
    
    message = extract_message_text(event.get("message", ""))
        
    # 空消息处理
    if not message:
        return
    
    logger.info(f"收到群{group_id}的消息：{message}")
    
    if user_id in config.master_list:
        if message.startswith("加群验证白名单"):
            args = message.split()
            if len(args) < 2:
                await send_group_msg(ws, group_id, "请提供正确的命令格式：\n加群验证白名单 [添加/移除/查看] <群号>(可选)\n加群验证白名单 阈值 <数字>\n加群验证白名单 时限 <数字>")
                return

            action, arg = args[1], args[2] if len(args) > 2 else group_id
            
            if action == "添加":
                success = await db.add_group(int(arg))
                await send_group_msg(ws, group_id, f"已将群{arg}添加到白名单" if success else "添加失败")
            elif action == "移除":
                success = await db.remove_group(int(arg))
                await send_group_msg(ws, group_id, f"已将群{arg}从白名单移除" if success else "移除失败")
            elif action == "查看":
                white_list = await db.get_white_list()
                await send_group_msg(ws, group_id, f"当前白名单群：{', '.join(map(str, white_list))}" if white_list else "白名单为空")
            elif action == "阈值":
                if len(args) < 3:
                    threshold = await db.get_threshold(int(arg))
                    await send_group_msg(ws, group_id, f"群{arg}的阈值为：{threshold}")
                else:
                    try:
                        new_threshold = int(arg)
                        success = await db.set_threshold(group_id, new_threshold)
                        await send_group_msg(ws, group_id, f"已将群{group_id}的阈值设置为：{new_threshold}" if success else "设置失败")
                    except ValueError:
                        await send_group_msg(ws, group_id, "请提供有效的阈值数字")
            elif action == "时限":
                if len(args) < 3:
                    timeout = await db.get_timeout(int(arg))
                    await send_group_msg(ws, group_id, f"群{arg}的验证时限为：{timeout}秒")
                else:
                    try:
                        new_timeout = int(arg)
                        success = await db.set_timeout(group_id, new_timeout)
                        await send_group_msg(ws, group_id, f"已将群{group_id}的验证时限设置为：{new_timeout}秒" if success else "设置失败")
                    except ValueError:
                        await send_group_msg(ws, group_id, "请提供有效的时限数字")
            else:
                await send_group_msg(ws, group_id, "请提供正确的操作：添加/移除")
                
            return   
    
    white_list = await db.get_white_list()
    if group_id not in white_list:
        return  # 不在白名单群中不需要验证
    
    key = (user_id, group_id)
    
    if key not in verification_pool:
        return
    
    # 验证消息内容
    if message == verification_pool[key]["code"]:
        verification_pool[key]["task"].cancel()
        del verification_pool[key]
        await send_group_msg(ws, group_id, f"验证成功，欢迎加入本群！")
        
async def handle_data(
    msg: aiohttp.WSMessage,
    ws: aiohttp.ClientWebSocketResponse
):
    """处理服务器发送的数据"""
    try:
        data = json.loads(msg.data)
        
        # 处理API响应
        if "echo" in data:
            if future := echo_map.get(data["echo"]):
                future.set_result(data)
            return
        
        # 处理事件
        if data.get("post_type") == "notice":
            if data["notice_type"] == "group_increase":
                asyncio.create_task(handle_group_increase(data, ws))
        elif data.get("post_type") == "message":
            if data["message_type"] == "group":
                asyncio.create_task(handle_group_msg(data, ws))
    except Exception as e:
        logger.error(f"处理消息出错: {e}")

async def websocket_client():
    """主WebSocket客户端"""
    async with aiohttp.ClientSession() as session:
        retry = 0
        while True:
            try:
                retry += 1
                logger.info(f"尝试连接到WebSocket服务器：{config.ws_url}({retry}/5)")

                async with session.ws_connect(config.ws_url) as ws:
                    retry = 0  # 连接成功后重置重试次数
                    logger.info("WebSocket连接成功")
                    
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        asyncio.create_task(handle_data(msg, ws))
            except Exception as e:
                logger.warning(f"WebSocket连接出错: {e}，30秒后重试")
                await asyncio.sleep(30)  # 连接失败后等待30秒后重试
                
                if retry >= 5:
                    logger.error("WebSocket连接失败，已达到最大重试次数，程序将退出")
                    raise ConnectionError("WebSocket连接失败")
                
async def main():
    """主函数"""
    await db.init_db()
    await websocket_client()

if __name__ == "__main__":
    asyncio.run(main())