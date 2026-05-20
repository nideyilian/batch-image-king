"""
缓存优化管理器
自动优化缓存策略，监控缓存性能，提供智能缓存建议
"""

import time
import threading
import psutil
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque

try:
    from .intelligent_render_cache import get_intelligent_cache, CacheStats
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


@dataclass
class CachePerformanceMetrics:
    """缓存性能指标"""
    timestamp: float
    hit_rate: float
    memory_usage_mb: float
    avg_render_time: float
    cache_efficiency: float
    system_memory_usage: float
    total_requests: int


@dataclass
class CacheOptimizationRecommendation:
    """缓存优化建议"""
    priority: str  # 'high', 'medium', 'low'
    category: str  # 'memory', 'performance', 'strategy'
    description: str
    action: str
    expected_improvement: str


class CacheOptimizationManager:
    """缓存优化管理器"""
    
    def __init__(self):
        self.cache = get_intelligent_cache() if CACHE_AVAILABLE else None
        self.performance_history: deque = deque(maxlen=100)  # 保留最近100个性能数据点
        self.optimization_history: List = []
        self.monitoring_enabled = False
        self.monitoring_thread = None
        self.monitoring_interval = 30.0  # 30秒监控间隔
        self._lock = threading.RLock()
        
        # 优化阈值
        self.thresholds = {
            'low_hit_rate': 60.0,        # 命中率低于60%
            'high_memory_usage': 80.0,   # 内存使用超过80%
            'slow_render_time': 1.0,     # 平均渲染时间超过1秒
            'system_memory_high': 85.0,  # 系统内存使用超过85%
        }
        
        print("[缓存优化] 缓存优化管理器初始化完成")
    
    def start_monitoring(self):
        """启动缓存性能监控"""
        if not CACHE_AVAILABLE:
            print("[缓存优化] 缓存系统不可用，无法启动监控")
            return
        
        if self.monitoring_enabled:
            return
        
        self.monitoring_enabled = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        # 不再设置为守护线程，避免程序退出时的锁竞争问题
        # daemon=True
        self.monitoring_thread.start()
        print("[缓存优化] 缓存性能监控已启动")
    
    def stop_monitoring(self):
        """停止缓存性能监控"""
        self.monitoring_enabled = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5.0)
        print("[缓存优化] 缓存性能监控已停止")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.monitoring_enabled:
            try:
                self._collect_performance_metrics()
                self._analyze_and_optimize()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                print(f"[缓存优化] 监控循环错误: {e}")
                time.sleep(self.monitoring_interval)
    
    def _collect_performance_metrics(self):
        """收集性能指标"""
        try:
            # 获取缓存统计
            cache_stats = self.cache.get_stats()
            
            # 获取系统内存使用率
            system_memory = psutil.virtual_memory()
            system_memory_usage = system_memory.percent
            
            # 创建性能指标
            metrics = CachePerformanceMetrics(
                timestamp=time.time(),
                hit_rate=cache_stats.hit_rate,
                memory_usage_mb=cache_stats.memory_usage_mb,
                avg_render_time=cache_stats.avg_render_time,
                cache_efficiency=cache_stats.cache_efficiency,
                system_memory_usage=system_memory_usage,
                total_requests=cache_stats.hit_count + cache_stats.miss_count
            )
            
            with self._lock:
                self.performance_history.append(metrics)
            
        except Exception as e:
            print(f"[缓存优化] 性能指标收集失败: {e}")
    
    def _analyze_and_optimize(self):
        """分析性能并自动优化"""
        if len(self.performance_history) < 3:  # 需要至少3个数据点
            return
        
        latest_metrics = self.performance_history[-1]
        recommendations = self._generate_recommendations(latest_metrics)
        
        # 执行高优先级的自动优化
        for rec in recommendations:
            if rec.priority == 'high':
                self._execute_optimization(rec)
    
    def _generate_recommendations(self, metrics: CachePerformanceMetrics) -> List[CacheOptimizationRecommendation]:
        """生成优化建议"""
        recommendations = []
        
        # 检查命中率
        if metrics.hit_rate < self.thresholds['low_hit_rate']:
            recommendations.append(CacheOptimizationRecommendation(
                priority='high',
                category='performance',
                description=f"缓存命中率过低 ({metrics.hit_rate:.1f}%)",
                action='increase_cache_size',
                expected_improvement='提高10-20%的渲染性能'
            ))
        
        # 检查内存使用
        if metrics.memory_usage_mb > 0:  # 有缓存数据
            cache_memory_ratio = (metrics.memory_usage_mb / 1024) * 100  # 转换为系统内存百分比的估算
            if cache_memory_ratio > self.thresholds['high_memory_usage']:
                recommendations.append(CacheOptimizationRecommendation(
                    priority='medium',
                    category='memory',
                    description=f"缓存内存使用过高 ({metrics.memory_usage_mb:.1f}MB)",
                    action='cleanup_cache',
                    expected_improvement='释放内存，提高系统稳定性'
                ))
        
        # 检查渲染时间
        if metrics.avg_render_time > self.thresholds['slow_render_time']:
            recommendations.append(CacheOptimizationRecommendation(
                priority='medium',
                category='performance',
                description=f"平均渲染时间过长 ({metrics.avg_render_time:.2f}秒)",
                action='optimize_render_strategy',
                expected_improvement='减少20-30%的渲染时间'
            ))
        
        # 检查系统内存
        if metrics.system_memory_usage > self.thresholds['system_memory_high']:
            recommendations.append(CacheOptimizationRecommendation(
                priority='high',
                category='memory',
                description=f"系统内存使用过高 ({metrics.system_memory_usage:.1f}%)",
                action='aggressive_cleanup',
                expected_improvement='释放系统内存，避免系统卡顿'
            ))
        
        # 检查缓存效率趋势
        if len(self.performance_history) >= 5:
            recent_efficiency = [m.cache_efficiency for m in list(self.performance_history)[-5:]]
            if len(recent_efficiency) >= 2:
                efficiency_trend = recent_efficiency[-1] - recent_efficiency[0]
                if efficiency_trend < -0.1:  # 效率下降超过0.1
                    recommendations.append(CacheOptimizationRecommendation(
                        priority='medium',
                        category='strategy',
                        description="缓存效率呈下降趋势",
                        action='refresh_cache_strategy',
                        expected_improvement='恢复缓存效率，提高整体性能'
                    ))
        
        return recommendations
    
    def _execute_optimization(self, recommendation: CacheOptimizationRecommendation):
        """执行优化建议"""
        try:
            action_map = {
                'increase_cache_size': self._increase_cache_size,
                'cleanup_cache': self._cleanup_cache,
                'optimize_render_strategy': self._optimize_render_strategy,
                'aggressive_cleanup': self._aggressive_cleanup,
                'refresh_cache_strategy': self._refresh_cache_strategy,
            }
            
            action_func = action_map.get(recommendation.action)
            if action_func:
                print(f"[缓存优化] 执行优化: {recommendation.description}")
                action_func()
                
                # 记录优化历史
                self.optimization_history.append({
                    'timestamp': time.time(),
                    'action': recommendation.action,
                    'description': recommendation.description,
                    'expected_improvement': recommendation.expected_improvement
                })
            
        except Exception as e:
            print(f"[缓存优化] 优化执行失败: {e}")
    
    def _increase_cache_size(self):
        """增加缓存大小"""
        # 这里可以动态调整缓存大小，目前只记录
        print("[缓存优化] 建议增加缓存大小以提高命中率")
    
    def _cleanup_cache(self):
        """清理缓存"""
        if self.cache:
            self.cache.optimize_cache()
            print("[缓存优化] 执行缓存清理")
    
    def _optimize_render_strategy(self):
        """优化渲染策略"""
        # 这里可以调整渲染参数，目前只记录
        print("[缓存优化] 建议优化渲染策略以减少渲染时间")
    
    def _aggressive_cleanup(self):
        """激进式清理"""
        if self.cache:
            # 清空一部分缓存以释放内存
            stats_before = self.cache.get_stats()
            self.cache.optimize_cache()
            stats_after = self.cache.get_stats()
            
            memory_freed = stats_before.memory_usage_mb - stats_after.memory_usage_mb
            print(f"[缓存优化] 激进式清理完成，释放 {memory_freed:.1f}MB 内存")
    
    def _refresh_cache_strategy(self):
        """刷新缓存策略"""
        # 清空部分老旧缓存，让系统重新学习
        if self.cache:
            self.cache.optimize_cache()
            print("[缓存优化] 缓存策略已刷新")
    
    def get_current_status(self) -> Dict:
        """获取当前缓存状态"""
        if not CACHE_AVAILABLE or not self.cache:
            return {
                'status': 'unavailable',
                'message': '缓存系统不可用'
            }
        
        try:
            stats = self.cache.get_stats()
            latest_metrics = self.performance_history[-1] if self.performance_history else None
            
            return {
                'status': 'active',
                'cache_stats': {
                    'total_entries': stats.total_entries,
                    'memory_usage_mb': stats.memory_usage_mb,
                    'hit_rate': stats.hit_rate,
                    'hit_count': stats.hit_count,
                    'miss_count': stats.miss_count,
                    'cache_efficiency': stats.cache_efficiency
                },
                'system_info': {
                    'memory_usage': latest_metrics.system_memory_usage if latest_metrics else 0,
                    'monitoring_enabled': self.monitoring_enabled,
                    'optimization_count': len(self.optimization_history)
                },
                'performance_trend': self._calculate_performance_trend()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'状态获取失败: {e}'
            }
    
    def _calculate_performance_trend(self) -> str:
        """计算性能趋势"""
        if len(self.performance_history) < 5:
            return 'insufficient_data'
        
        recent_metrics = list(self.performance_history)[-5:]
        hit_rates = [m.hit_rate for m in recent_metrics]
        
        # 简单的趋势分析
        if len(hit_rates) >= 2:
            trend = hit_rates[-1] - hit_rates[0]
            if trend > 5:
                return 'improving'
            elif trend < -5:
                return 'declining'
            else:
                return 'stable'
        
        return 'unknown'
    
    def generate_optimization_report(self) -> Dict:
        """生成优化报告"""
        if not self.performance_history:
            return {
                'status': 'no_data',
                'message': '缺少性能数据'
            }
        
        latest_metrics = self.performance_history[-1]
        recommendations = self._generate_recommendations(latest_metrics)
        
        # 计算性能统计
        if len(self.performance_history) >= 2:
            hit_rates = [m.hit_rate for m in self.performance_history]
            memory_usage = [m.memory_usage_mb for m in self.performance_history]
            
            avg_hit_rate = sum(hit_rates) / len(hit_rates)
            max_memory = max(memory_usage)
            current_efficiency = latest_metrics.cache_efficiency
            
        else:
            avg_hit_rate = latest_metrics.hit_rate
            max_memory = latest_metrics.memory_usage_mb
            current_efficiency = latest_metrics.cache_efficiency
        
        return {
            'status': 'success',
            'report_time': time.time(),
            'performance_summary': {
                'current_hit_rate': latest_metrics.hit_rate,
                'average_hit_rate': avg_hit_rate,
                'current_memory_mb': latest_metrics.memory_usage_mb,
                'peak_memory_mb': max_memory,
                'cache_efficiency': current_efficiency,
                'system_memory_usage': latest_metrics.system_memory_usage
            },
            'recommendations': [
                {
                    'priority': rec.priority,
                    'category': rec.category,
                    'description': rec.description,
                    'expected_improvement': rec.expected_improvement
                }
                for rec in recommendations
            ],
            'optimization_history': self.optimization_history[-10:],  # 最近10次优化
            'performance_trend': self._calculate_performance_trend()
        }
    
    def force_optimization(self):
        """强制执行缓存优化"""
        if not CACHE_AVAILABLE or not self.cache:
            print("[缓存优化] 缓存系统不可用")
            return
        
        print("[缓存优化] 开始强制优化...")
        
        # 收集当前指标
        self._collect_performance_metrics()
        
        if self.performance_history:
            latest_metrics = self.performance_history[-1]
            recommendations = self._generate_recommendations(latest_metrics)
            
            # 执行所有高优先级建议
            for rec in recommendations:
                if rec.priority in ['high', 'medium']:
                    self._execute_optimization(rec)
            
            print(f"[缓存优化] 强制优化完成，执行了 {len(recommendations)} 个建议")
        else:
            print("[缓存优化] 无性能数据，仅执行基础优化")
            self.cache.optimize_cache()


# 全局缓存优化管理器实例
_cache_optimizer = None

def get_cache_optimizer() -> CacheOptimizationManager:
    """获取全局缓存优化管理器"""
    global _cache_optimizer
    if _cache_optimizer is None:
        _cache_optimizer = CacheOptimizationManager()
    return _cache_optimizer


def start_cache_monitoring():
    """启动缓存监控"""
    optimizer = get_cache_optimizer()
    optimizer.start_monitoring()


def stop_cache_monitoring():
    """停止缓存监控"""
    optimizer = get_cache_optimizer()
    optimizer.stop_monitoring()


def force_cache_optimization():
    """强制执行缓存优化"""
    optimizer = get_cache_optimizer()
    optimizer.force_optimization()


def get_cache_status():
    """获取缓存状态"""
    optimizer = get_cache_optimizer()
    return optimizer.get_current_status()


def generate_cache_report():
    """生成缓存报告"""
    optimizer = get_cache_optimizer()
    return optimizer.generate_optimization_report()