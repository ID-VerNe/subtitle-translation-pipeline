# -*- coding: utf-8 -*-
import asyncio
import time
import collections
import threading
import aiohttp
import logging
from typing import Optional, Dict, Any, Union, Callable, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PERMANENTLY_FAILED = "permanently_failed"


@dataclass
class Task:
    """任务对象"""
    id: str
    func: Callable
    args: tuple
    kwargs: dict
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    assigned_api: Optional[int] = None


class TaskQueue:
    """任务队列管理器"""
    def __init__(self):
        self._queue = asyncio.Queue()
        self._tasks: Dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._task_counter = 0

    async def submit(self, func: Callable, *args, **kwargs) -> str:
        """提交任务到队列"""
        async with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}_{time.time():.6f}"
        
        task = Task(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs
        )
        
        async with self._lock:
            self._tasks[task_id] = task
        
        await self._queue.put(task)
        logger.debug(f"Task {task_id} submitted to queue")
        return task_id

    async def get(self) -> Optional[Task]:
        """获取下一个待处理任务"""
        try:
            task = await self._queue.get()
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            return task
        except asyncio.CancelledError:
            return None

    async def mark_completed(self, task_id: str, result: Any):
        """标记任务完成"""
        async with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                logger.debug(f"Task {task_id} completed")

    async def mark_failed(self, task_id: str, error: Exception, max_retries: int = 3) -> bool:
        """标记任务失败，返回是否需要重试"""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            
            task = self._tasks[task_id]
            task.error = error
            task.retry_count += 1
            
            if task.retry_count >= max_retries:
                task.status = TaskStatus.PERMANENTLY_FAILED
                task.completed_at = time.time()
                logger.warning(f"Task {task_id} permanently failed after {max_retries} retries")
                return False
            else:
                task.status = TaskStatus.FAILED
                logger.debug(f"Task {task_id} failed, will retry ({task.retry_count}/{max_retries})")
                return True

    async def requeue(self, task_id: str):
        """将任务重新加入队列"""
        async with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = TaskStatus.PENDING
                task.started_at = None
                task.assigned_api = None
        
        await self._queue.put(self._tasks[task_id])
        logger.debug(f"Task {task_id} requeued")

    def get_stats(self) -> Dict[str, int]:
        """获取队列统计信息"""
        stats = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "permanently_failed": 0
        }
        for task in self._tasks.values():
            stats[task.status.value] += 1
        return stats


class APIHealth:
    """API健康状态监控"""
    def __init__(self, window_size: int = 100):
        self.success_count = 0
        self.failure_count = 0
        self.response_times = collections.deque(maxlen=window_size)
        self.last_used = 0.0
        self.consecutive_failures = 0
        self._lock = asyncio.Lock()

    async def record_success(self, response_time: float):
        """记录成功请求"""
        async with self._lock:
            self.success_count += 1
            self.response_times.append(response_time)
            self.consecutive_failures = 0
            self.last_used = time.time()

    async def record_failure(self):
        """记录失败请求"""
        async with self._lock:
            self.failure_count += 1
            self.consecutive_failures += 1
            self.last_used = time.time()

    def get_success_rate(self) -> float:
        """获取成功率"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 1.0
        return self.success_count / total

    def get_avg_response_time(self) -> float:
        """获取平均响应时间"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def is_healthy(self, max_consecutive_failures: int = 3) -> bool:
        """检查API是否健康"""
        return self.consecutive_failures < max_consecutive_failures


class RateLimiter:
    """速率控制器：管理 RPM (每分钟请求数) 和 TPM (每分钟 Token 数)"""
    def __init__(self, rpm: float, tpm: float):
        self.rpm = rpm
        self.tpm = tpm
        self.request_interval = 60.0 / rpm if rpm > 0 else 0
        self.last_request_time = 0.0
        
        # TPM 窗口统计 (使用滑动窗口记录过去 60 秒的消耗)
        self.token_window = collections.deque() # 存储格式: (timestamp, token_count)
        self.window_size = 60.0
        self.lock = asyncio.Lock()

    def _clean_window(self):
        """清理超过 60 秒的旧记录"""
        now = time.time()
        while self.token_window and now - self.token_window[0][0] > self.window_size:
            self.token_window.popleft()

    def get_current_tpm(self) -> int:
        """获取当前窗口内的总 Token 消耗"""
        self._clean_window()
        return sum(item[1] for item in self.token_window)

    async def wait_async(self, estimated_tokens: int = 0):
        """异步等待直到符合 RPM 和 TPM 要求"""
        while True:
            async with self.lock:
                now = time.time()
                # 1. 检查 RPM 硬间隔
                time_since_last = now - self.last_request_time
                wait_rpm = max(0, self.request_interval - time_since_last)
                
                # 2. 检查 TPM 剩余额度
                current_tpm = self.get_current_tpm()
                if self.tpm > 0 and current_tpm + estimated_tokens > self.tpm and self.token_window:
                    # 需等待窗口中最早的记录失效
                    wait_tpm = self.window_size - (now - self.token_window[0][0]) + 0.1
                else:
                    wait_tpm = 0

                total_wait = max(wait_rpm, wait_tpm)
                if total_wait <= 0:
                    self.last_request_time = time.time()
                    return # 拿到令牌
            
            # 在锁外等待
            await asyncio.sleep(total_wait)

    def add_tokens(self, count: int):
        """记录消耗的 Token"""
        self.token_window.append((time.time(), count))


class AsyncRateLimitedSession:
    """异步封装：管理 aiohttp.ClientSession 并自动处理限速"""
    def __init__(self, api_key: str, rpm: int = 60, tpm: int = 100000, concurrency: int = 4):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json"
        }
        self.limiter = RateLimiter(rpm, tpm)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.max_concurrency = concurrency
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        if not self._session:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def post(self, url: str, **kwargs):
        """发送 POST 请求，自动处理限速"""
        # 确保 session 已创建
        if not self._session:
            self._session = aiohttp.ClientSession(headers=self.headers)

        # 预估 Token 消耗
        prompt = ""
        messages = kwargs.get("json", {}).get("messages", [])
        if messages:
            prompt = messages[-1].get("content", "")
        # 粗略预估：输入字数 * 2 + 预留输出 1000
        est_tokens = len(prompt) * 2 + 1000
        
        async with self.semaphore: # 限制并发
            await self.limiter.wait_async(est_tokens) # 限制频率
            
            try:
                response = await self._session.post(url, **kwargs)
                
                # 如果成功，自动更新 TPM 统计
                if response.status == 200:
                    if not kwargs.get("stream", False):
                        try:
                            # 注意：这里我们不能 await response.json() 否则会消耗掉 response
                            # 但我们需要 usage 信息。
                            # aiohttp 的 response.json() 默认会读取并缓存，所以后面还可以读取。
                            resp_data = await response.json()
                            actual_tokens = resp_data.get("usage", {}).get("total_tokens", est_tokens)
                            self.limiter.add_tokens(actual_tokens)
                        except:
                            pass
                elif response.status == 429:
                    logger.warning("Triggered 429 Too Many Requests, cooling down...")
                    await asyncio.sleep(10)
                    
                return response
            except Exception as e:
                logger.error(f"Request Error: {e}")
                raise


class SmartLoadBalancer:
    """智能负载均衡器：支持任务队列和智能API选择"""
    def __init__(self, sessions: List[AsyncRateLimitedSession], max_retries: int = 3):
        self.sessions = sessions
        self.max_retries = max_retries
        self.task_queue = TaskQueue()
        self.api_health = [APIHealth() for _ in range(len(sessions))]
        self._lock = asyncio.Lock()
        self._shutdown = False
        self._workers: List[asyncio.Task] = []
        self._results: Dict[str, Any] = {}
        self._initialized = False
        
        # 计算总并发数
        self.total_concurrency = sum(s.max_concurrency for s in sessions)
        logger.info(f"SmartLoadBalancer initialized with {len(sessions)} APIs, "
                   f"total concurrency: {self.total_concurrency}")

    async def _ensure_initialized(self):
        """确保工作协程已启动"""
        if not self._initialized:
            async with self._lock:
                if not self._initialized:
                    # 启动工作协程
                    for i in range(self.total_concurrency):
                        worker = asyncio.create_task(self._worker_loop(i))
                        self._workers.append(worker)
                    
                    # 初始化所有子会话
                    for s in self.sessions:
                        await s.__aenter__()
                    
                    self._initialized = True
                    logger.debug("SmartLoadBalancer workers started")

    async def __aenter__(self):
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._initialized:
            return
            
        self._shutdown = True
        
        # 取消所有工作协程
        for worker in self._workers:
            worker.cancel()
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        # 关闭所有子会话
        for s in self.sessions:
            await s.__aexit__(exc_type, exc_val, exc_tb)
        
        self._initialized = False

    def _select_best_api(self) -> int:
        """选择最佳API（基于成功率和当前负载）"""
        best_idx = 0
        best_score = -1.0
        
        for i, (session, health) in enumerate(zip(self.sessions, self.api_health)):
            # 跳过不健康的API
            if not health.is_healthy():
                continue
            
            # 计算得分：成功率 * 可用并发 slots / (平均响应时间 + 1)
            success_rate = health.get_success_rate()
            available_slots = session.semaphore._value
            avg_response_time = health.get_avg_response_time()
            
            # 如果API从未使用过，给予较高的初始分数
            if health.success_count + health.failure_count == 0:
                score = 1.0 * available_slots
            else:
                score = success_rate * available_slots / (avg_response_time + 1.0)
            
            if score > best_score:
                best_score = score
                best_idx = i
        
        return best_idx

    async def _worker_loop(self, worker_id: int):
        """工作协程：从队列获取任务并执行"""
        logger.debug(f"Worker {worker_id} started")
        while not self._shutdown:
            try:
                task = await self.task_queue.get()
                if task is None:
                    break
                
                # 选择最佳API
                api_idx = self._select_best_api()
                task.assigned_api = api_idx
                session = self.sessions[api_idx]
                health = self.api_health[api_idx]
                
                start_time = time.time()
                try:
                    # 执行任务
                    result = await task.func(session, *task.args, **task.kwargs)
                    
                    # 记录成功
                    response_time = time.time() - start_time
                    await health.record_success(response_time)
                    
                    # 标记完成
                    await self.task_queue.mark_completed(task.id, result)
                    self._results[task.id] = result
                    
                except Exception as e:
                    # 记录失败
                    await health.record_failure()
                    
                    # 检查是否需要重试
                    should_retry = await self.task_queue.mark_failed(task.id, e, self.max_retries)
                    if should_retry:
                        # 重新入队，使用不同的API
                        await self.task_queue.requeue(task.id)
                    else:
                        self._results[task.id] = e
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.debug(f"Worker {worker_id} stopped")

    async def submit(self, func: Callable, *args, **kwargs) -> str:
        """提交任务到队列"""
        await self._ensure_initialized()
        return await self.task_queue.submit(func, *args, **kwargs)

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """等待任务完成并返回结果"""
        await self._ensure_initialized()
        start_time = time.time()
        while True:
            if task_id in self._results:
                result = self._results[task_id]
                if isinstance(result, Exception):
                    raise result
                return result
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} timed out")
            
            await asyncio.sleep(0.1)

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """提交任务并等待结果（便捷方法）"""
        await self._ensure_initialized()
        task_id = await self.submit(func, *args, **kwargs)
        return await self.wait_for_task(task_id)

    def get_stats(self) -> Dict[str, Any]:
        """获取负载均衡器统计信息"""
        queue_stats = self.task_queue.get_stats()
        api_stats = []
        for i, health in enumerate(self.api_health):
            api_stats.append({
                "api_index": i,
                "success_rate": health.get_success_rate(),
                "avg_response_time": health.get_avg_response_time(),
                "success_count": health.success_count,
                "failure_count": health.failure_count,
                "is_healthy": health.is_healthy(),
                "available_slots": self.sessions[i].semaphore._value
            })
        
        return {
            "queue": queue_stats,
            "apis": api_stats,
            "total_concurrency": self.total_concurrency
        }


# 保持向后兼容
class LoadBalancedSession:
    """负载均衡封装：在多个 AsyncRateLimitedSession 之间轮询请求（已弃用，使用 SmartLoadBalancer）"""
    def __init__(self, sessions: list[AsyncRateLimitedSession]):
        self.sessions = sessions
        self._index = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        # 注意：子会话的 __aenter__ 应该在创建时或此处统一处理
        for s in self.sessions:
            await s.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for s in self.sessions:
            await s.__aexit__(exc_type, exc_val, exc_tb)

    async def post(self, url: str, **kwargs):
        """轮询选择一个子会话发送请求"""
        async with self._lock:
            session = self.sessions[self._index % len(self.sessions)]
            self._index += 1
            
        # 实际的请求在锁外执行，允许并行
        return await session.post(url, **kwargs)
