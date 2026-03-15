#!/usr/bin/env python3
"""
Claw 负载监控系统 - 数据采集服务
版本: v1.0.0
"""

import os
import json
import time
import asyncio
import sqlite3
import redis.asyncio as redis
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import psutil

# ==========================================
# 配置
# ==========================================
CONFIG = {
    # OpenClaw 会话目录
    "SESSIONS_DIR": "/root/.openclaw/agents/main/sessions",
    
    # 活跃会话判定时间 (秒)
    "ACTIVE_THRESHOLD": 600,  # 10分钟
    
    # Redis 配置 (Upstash 或本地)
    "REDIS_URL": os.getenv("REDIS_URL", "redis://localhost:6379"),
    "REDIS_TOKEN": os.getenv("REDIS_TOKEN", None),
    
    # 数据更新间隔
    "UPDATE_INTERVAL": 15,  # 秒
    
    # SQLite 历史数据库
    "HISTORY_DB": "/var/lib/cognitive_monitor/history.db",
    
    # 保留历史天数
    "HISTORY_RETENTION_DAYS": 30,
}

# ==========================================
# 任务标签映射
# ==========================================
TASK_LABELS = {
    "code": "代码开发",
    "data": "数据分析", 
    "doc": "文档处理",
    "ops": "系统运维",
    "qa": "知识问答",
    "creative": "创意生成",
    "review": "代码审查",
    "research": "技术研究",
    "meeting": "会议辅助",
    "learning": "学习辅导",
    "pm": "项目管理",
    "comm": "沟通协调",
}

class CognitiveMonitor:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.db_conn: Optional[sqlite3.Connection] = None
        self.running = False
        
    async def init(self):
        """初始化连接"""
        # 连接 Redis
        try:
            if CONFIG["REDIS_TOKEN"]:
                # Upstash 模式
                self.redis_client = redis.Redis(
                    host=CONFIG["REDIS_URL"].replace("https://", "").replace("redis://", ""),
                    port=6379,
                    password=CONFIG["REDIS_TOKEN"],
                    ssl=True,
                    decode_responses=True
                )
            else:
                # 本地 Redis
                self.redis_client = redis.from_url(
                    CONFIG["REDIS_URL"],
                    decode_responses=True
                )
            await self.redis_client.ping()
            print("✅ Redis 连接成功")
        except Exception as e:
            print(f"⚠️ Redis 连接失败: {e}")
            self.redis_client = None
        
        # 初始化 SQLite
        try:
            os.makedirs(os.path.dirname(CONFIG["HISTORY_DB"]), exist_ok=True)
            self.db_conn = sqlite3.connect(CONFIG["HISTORY_DB"], check_same_thread=False)
            self._init_db()
            print("✅ SQLite 连接成功")
        except Exception as e:
            print(f"⚠️ SQLite 连接失败: {e}")
            self.db_conn = None
    
    def _init_db(self):
        """初始化数据库表"""
        cursor = self.db_conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS load_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                score REAL,
                active_sessions INTEGER,
                pending INTEGER,
                processing INTEGER,
                cpu REAL,
                memory REAL
            )
        """)
        self.db_conn.commit()
    
    def _get_session_files(self) -> List[Path]:
        """获取所有会话文件"""
        sessions_dir = Path(CONFIG["SESSIONS_DIR"])
        if not sessions_dir.exists():
            return []
        
        # 获取所有 .jsonl 文件
        return list(sessions_dir.glob("*.jsonl"))
    
    def _analyze_session(self, filepath: Path) -> Dict[str, Any]:
        """分析单个会话状态"""
        try:
            stat = filepath.stat()
            last_modified = stat.st_mtime
            age = time.time() - last_modified
            
            # 读取最后几行消息
            messages = []
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    messages = [json.loads(line) for line in lines[-10:] if line.strip()]
            except:
                pass
            
            # 分析消息状态
            last_message_time = None
            pending_count = 0
            processing = False
            token_count = 0
            
            for msg in messages:
                msg_time = msg.get('timestamp', 0)
                if msg_time > last_message_time:
                    last_message_time = msg_time
                
                # 检测待处理消息 (用户发送但未回复)
                if msg.get('role') == 'user' and not msg.get('processed', False):
                    pending_count += 1
                
                # 检测处理中状态
                if msg.get('status') == 'processing':
                    processing = True
                
                # 估算 Token 数
                content = msg.get('content', '')
                token_count += len(content) // 4  # 粗略估算
            
            # 判断会话状态
            if processing:
                status = 'processing'
            elif pending_count > 0:
                status = 'pending'
            elif age < CONFIG["ACTIVE_THRESHOLD"]:
                status = 'idle'
            else:
                status = 'inactive'
            
            # 生成智能标签
            label = self._generate_label(filepath.stem, messages)
            
            return {
                'id': filepath.stem,
                'status': status,
                'pending': pending_count,
                'processing': processing,
                'tokens': token_count,
                'last_active': age,
                'label': label,
            }
            
        except Exception as e:
            return {
                'id': filepath.stem,
                'status': 'error',
                'error': str(e)
            }
    
    def _generate_label(self, session_id: str, messages: List[Dict]) -> str:
        """生成会话标签"""
        # 基于会话 ID 和消息内容推断标签
        content = ' '.join([m.get('content', '') for m in messages[-5:]]).lower()
        
        # 关键词匹配
        if any(kw in content for kw in ['代码', '编程', 'python', 'javascript', 'bug', 'error']):
            return TASK_LABELS.get('code', '代码开发')
        elif any(kw in content for kw in ['数据', '分析', '统计', '图表', 'csv', 'excel']):
            return TASK_LABELS.get('data', '数据分析')
        elif any(kw in content for kw in ['文档', '总结', '翻译', 'markdown', '报告']):
            return TASK_LABELS.get('doc', '文档处理')
        elif any(kw in content for kw in ['服务器', '部署', 'docker', 'nginx', 'ssh']):
            return TASK_LABELS.get('ops', '系统运维')
        elif any(kw in content for kw in ['创意', '文案', '设计', '故事', 'idea']):
            return TASK_LABELS.get('creative', '创意生成')
        elif any(kw in content for kw in ['pr', 'review', '审查', '代码质量']):
            return TASK_LABELS.get('review', '代码审查')
        else:
            return TASK_LABELS.get('qa', '知识问答')
    
    def _calculate_score(self, sessions: List[Dict]) -> Dict[str, Any]:
        """计算认知负载评分"""
        active_sessions = [s for s in sessions if s['status'] != 'inactive']
        pending_tasks = sum(s['pending'] for s in sessions)
        processing_tasks = [s for s in sessions if s['status'] == 'processing']
        
        # 基础评分
        base_score = 50
        
        # 等待评分 (基于最长等待时间)
        max_wait = 0
        wait_score = 0
        for s in sessions:
            if s['status'] in ['pending', 'processing']:
                wait = s.get('last_active', 0)
                if wait > max_wait:
                    max_wait = wait
        
        if max_wait < 10:
            wait_score = 25
        elif max_wait < 30:
            wait_score = 40
        elif max_wait < 60:
            wait_score = 65
        else:
            wait_score = 85
        
        # Token 评分 (基于处理中任务)
        token_score = 0
        total_tokens = sum(s.get('tokens', 0) for s in processing_tasks)
        if total_tokens > 200000:
            token_score = 80
        elif total_tokens > 100000:
            token_score = 50
        elif total_tokens > 50000:
            token_score = 30
        elif total_tokens > 10000:
            token_score = 10
        
        # 处理加成
        processing_bonus = min(len(processing_tasks) * 3, 15)
        
        # 最终评分
        final_score = base_score + max(wait_score, token_score) + processing_bonus
        final_score = min(final_score, 100)
        
        # 预计响应时间
        est_response = (
            len(processing_tasks) * 30 +
            min(60, total_tokens / 50000 * 30) +
            pending_tasks * 15
        )
        
        return {
            'score': final_score,
            'active_sessions': len(active_sessions),
            'pending': pending_tasks,
            'processing': len(processing_tasks),
            'max_wait': int(max_wait),
            'est_response': int(est_response),
            'tasks': [
                {
                    'id': s['id'],
                    'name': s.get('label', '未知任务'),
                    'status': s['status'],
                    'tokens': s.get('tokens', 0),
                    'last_active': int(s.get('last_active', 0))
                }
                for s in active_sessions[:10]  # 最多显示10个
            ]
        }
    
    def _get_system_stats(self) -> Dict[str, float]:
        """获取系统资源使用情况"""
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            return {'cpu': cpu, 'memory': memory}
        except:
            return {'cpu': 0, 'memory': 0}
    
    async def _save_to_redis(self, data: Dict):
        """保存到 Redis"""
        if not self.redis_client:
            return
        
        try:
            await self.redis_client.set(
                'cognitive_load',
                json.dumps(data),
                ex=300  # 5分钟过期
            )
        except Exception as e:
            print(f"Redis 写入失败: {e}")
    
    def _save_to_sqlite(self, data: Dict):
        """保存到 SQLite 历史记录"""
        if not self.db_conn:
            return
        
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO load_history 
                (score, active_sessions, pending, processing, cpu, memory)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                data['score'],
                data['active_sessions'],
                data['pending'],
                data['processing'],
                data.get('cpu', 0),
                data.get('memory', 0)
            ))
            self.db_conn.commit()
            
            # 清理旧数据
            self._cleanup_old_data()
            
        except Exception as e:
            print(f"SQLite 写入失败: {e}")
    
    def _cleanup_old_data(self):
        """清理过期历史数据"""
        try:
            cutoff = datetime.now() - timedelta(days=CONFIG["HISTORY_RETENTION_DAYS"])
            cursor = self.db_conn.cursor()
            cursor.execute(
                "DELETE FROM load_history WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            self.db_conn.commit()
        except Exception as e:
            print(f"清理旧数据失败: {e}")
    
    async def collect(self):
        """执行一次数据采集"""
        # 获取会话数据
        session_files = self._get_session_files()
        sessions = [self._analyze_session(f) for f in session_files]
        
        # 计算评分
        data = self._calculate_score(sessions)
        
        # 获取系统状态
        stats = self._get_system_stats()
        data.update(stats)
        
        # 添加元数据
        data['timestamp'] = time.time()
        data['agent_status'] = 'active' if data['score'] < 75 else 'busy'
        
        return data
    
    async def run(self):
        """主循环"""
        print("🚀 Claw 负载监控服务启动")
        print(f"📁 会话目录: {CONFIG['SESSIONS_DIR']}")
        print(f"⏱️  更新间隔: {CONFIG['UPDATE_INTERVAL']}秒")
        print()
        
        self.running = True
        
        while self.running:
            try:
                start_time = time.time()
                
                # 采集数据
                data = await self.collect()
                
                # 保存数据
                await self._save_to_redis(data)
                self._save_to_sqlite(data)
                
                # 打印状态
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"评分: {data['score']:.0f}% | "
                      f"会话: {data['active_sessions']} | "
                      f"待处理: {data['pending']} | "
                      f"处理中: {data['processing']} | "
                      f"CPU: {data['cpu']:.0f}%")
                
                # 计算睡眠时间
                elapsed = time.time() - start_time
                sleep_time = max(0, CONFIG["UPDATE_INTERVAL"] - elapsed)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                print(f"❌ 采集错误: {e}")
                await asyncio.sleep(CONFIG["UPDATE_INTERVAL"])
    
    def stop(self):
        """停止服务"""
        self.running = False
        if self.db_conn:
            self.db_conn.close()


async def main():
    monitor = CognitiveMonitor()
    await monitor.init()
    
    try:
        await monitor.run()
    except KeyboardInterrupt:
        print("\n🛑 收到停止信号")
        monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
