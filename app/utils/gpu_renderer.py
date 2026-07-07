"""
GPU加速渲染器
使用OpenGL进行高性能图像处理和合成
完全兼容现有的PIL渲染管线
"""


import os as _os
_BTPW_VERBOSE = _os.environ.get("BTPW_VERBOSE_LOG", "0").strip().lower() in ("1", "true", "yes", "on")
_ALWAYS_PRINT_KW = ("[ERROR]", "[CRITICAL]", "[严重错误]", "错误", "失败", "Exception", "Traceback", "[WARNING]")
def print(*args, **kwargs):
    if _BTPW_VERBOSE:
        __builtins__["print"](*args, **kwargs)
        return
    try:
        msg = " ".join(str(a) for a in args)
    except Exception:
        msg = ""
    if any(kw in msg for kw in _ALWAYS_PRINT_KW):
        __builtins__["print"](*args, **kwargs)

import os
import sys
import time
import threading
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from PIL import Image
import numpy as np

# OpenGL相关导入
try:
    import OpenGL.GL as gl
    import OpenGL.GL.shaders as shaders
    from OpenGL.arrays import vbo
    from OpenGL.GL import glGenTextures, glBindTexture, glTexImage2D, glTexParameteri
    from OpenGL.GL import GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE, GL_LINEAR, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER
    from OpenGL.GL import glGenFramebuffers, glBindFramebuffer, glFramebufferTexture2D, GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0
    from OpenGL.GL import glViewport, glClear, GL_COLOR_BUFFER_BIT, glReadPixels
    from OpenGL.GL import glUseProgram, glUniform1f, glUniform2f, glUniform4f, glUniformMatrix4fv
    from OpenGL.GL import glGenVertexArrays, glBindVertexArray, glGenBuffers, glBindBuffer, glBufferData
    from OpenGL.GL import GL_ARRAY_BUFFER, GL_STATIC_DRAW, glVertexAttribPointer, glEnableVertexAttribArray
    from OpenGL.GL import glDrawArrays, GL_TRIANGLES, glEnable, glBlendFunc, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False
    print("[GPU渲染] OpenGL不可用，GPU加速将被禁用")

# EGL/无头渲染支持
try:
    if OPENGL_AVAILABLE:
        import OpenGL.EGL as egl
        EGL_AVAILABLE = True
except ImportError:
    EGL_AVAILABLE = False


@dataclass
class GPURenderConfig:
    """GPU渲染配置"""
    enable_gpu: bool = True
    max_texture_size: int = 8192
    use_mipmaps: bool = True
    enable_multisampling: bool = True
    samples: int = 4
    prefer_dedicated_gpu: bool = True
    fallback_to_cpu: bool = True


@dataclass
class LayerGPUData:
    """图层GPU数据"""
    texture_id: int
    width: int
    height: int
    x: float
    y: float
    opacity: float
    blend_mode: str
    effects: Dict[str, Any]


class GPUShaderManager:
    """GPU着色器管理器"""
    
    def __init__(self):
        self.shaders = {}
        self.programs = {}
        self._init_shaders()
    
    def _init_shaders(self):
        """初始化着色器"""
        # 顶点着色器
        self.vertex_shader_source = """
        #version 330 core
        layout (location = 0) in vec3 aPos;
        layout (location = 1) in vec2 aTexCoord;
        
        out vec2 TexCoord;
        
        uniform mat4 transform;
        
        void main()
        {
            gl_Position = transform * vec4(aPos, 1.0);
            TexCoord = aTexCoord;
        }
        """
        
        # 基础片段着色器
        self.fragment_shader_source = """
        #version 330 core
        out vec4 FragColor;
        
        in vec2 TexCoord;
        
        uniform sampler2D ourTexture;
        uniform float opacity;
        uniform vec4 colorMultiplier;
        
        void main()
        {
            vec4 texColor = texture(ourTexture, TexCoord);
            FragColor = texColor * colorMultiplier * opacity;
        }
        """
        
        # 圆角着色器
        self.corner_radius_shader_source = """
        #version 330 core
        out vec4 FragColor;
        
        in vec2 TexCoord;
        
        uniform sampler2D ourTexture;
        uniform float opacity;
        uniform float cornerRadius;
        uniform vec2 textureSize;
        
        void main()
        {
            vec4 texColor = texture(ourTexture, TexCoord);
            
            // 计算到边角的距离
            vec2 pos = TexCoord * textureSize;
            vec2 corner = vec2(cornerRadius);
            
            // 检查是否在圆角区域
            vec2 cornerDist = max(vec2(0.0), abs(pos - textureSize * 0.5) - (textureSize * 0.5 - corner));
            float dist = length(cornerDist);
            
            // 平滑的圆角遮罩
            float alpha = 1.0 - smoothstep(cornerRadius - 1.0, cornerRadius, dist);
            
            FragColor = vec4(texColor.rgb, texColor.a * alpha * opacity);
        }
        """
        
        # 高斯模糊着色器
        self.blur_shader_source = """
        #version 330 core
        out vec4 FragColor;
        
        in vec2 TexCoord;
        
        uniform sampler2D ourTexture;
        uniform vec2 blurDirection;
        uniform float blurRadius;
        uniform vec2 textureSize;
        
        void main()
        {
            vec4 color = vec4(0.0);
            vec2 texelSize = 1.0 / textureSize;
            
            // 高斯权重
            float weights[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
            
            color += texture(ourTexture, TexCoord) * weights[0];
            
            for(int i = 1; i < 5; ++i)
            {
                color += texture(ourTexture, TexCoord + blurDirection * texelSize * float(i) * blurRadius) * weights[i];
                color += texture(ourTexture, TexCoord - blurDirection * texelSize * float(i) * blurRadius) * weights[i];
            }
            
            FragColor = color;
        }
        """
    
    def compile_shader(self, shader_type: int, source: str) -> int:
        """编译着色器"""
        shader = gl.glCreateShader(shader_type)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        
        # 检查编译错误
        if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
            error = gl.glGetShaderInfoLog(shader)
            gl.glDeleteShader(shader)
            raise RuntimeError(f"着色器编译失败: {error}")
        
        return shader
    
    def create_program(self, vertex_source: str, fragment_source: str) -> int:
        """创建着色器程序"""
        vertex_shader = self.compile_shader(gl.GL_VERTEX_SHADER, vertex_source)
        fragment_shader = self.compile_shader(gl.GL_FRAGMENT_SHADER, fragment_source)
        
        program = gl.glCreateProgram()
        gl.glAttachShader(program, vertex_shader)
        gl.glAttachShader(program, fragment_shader)
        gl.glLinkProgram(program)
        
        # 检查链接错误
        if not gl.glGetProgramiv(program, gl.GL_LINK_STATUS):
            error = gl.glGetProgramInfoLog(program)
            gl.glDeleteProgram(program)
            raise RuntimeError(f"着色器程序链接失败: {error}")
        
        # 清理着色器
        gl.glDeleteShader(vertex_shader)
        gl.glDeleteShader(fragment_shader)
        
        return program
    
    def get_program(self, program_name: str) -> int:
        """获取着色器程序"""
        if program_name not in self.programs:
            if program_name == "basic":
                self.programs[program_name] = self.create_program(
                    self.vertex_shader_source, self.fragment_shader_source
                )
            elif program_name == "corner_radius":
                self.programs[program_name] = self.create_program(
                    self.vertex_shader_source, self.corner_radius_shader_source
                )
            elif program_name == "blur":
                self.programs[program_name] = self.create_program(
                    self.vertex_shader_source, self.blur_shader_source
                )
            else:
                raise ValueError(f"未知的着色器程序: {program_name}")
        
        return self.programs[program_name]


class GPUContext:
    """GPU上下文管理器"""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.context = None
        self.display = None
        self.surface = None
        self.framebuffer = None
        self.color_texture = None
        self.is_initialized = False
        
    def initialize(self) -> bool:
        """初始化GPU上下文"""
        try:
            if not OPENGL_AVAILABLE:
                return False
            
            # 尝试创建无头渲染上下文
            if EGL_AVAILABLE:
                return self._init_egl_context()
            else:
                # 回退到其他方法
                return self._init_fallback_context()
                
        except Exception as e:
            print(f"[GPU渲染] GPU上下文初始化失败: {e}")
            return False
    
    def _init_egl_context(self) -> bool:
        """初始化EGL上下文"""
        try:
            # 获取默认显示
            self.display = egl.eglGetDisplay(egl.EGL_DEFAULT_DISPLAY)
            if self.display == egl.EGL_NO_DISPLAY:
                return False
            
            # 初始化EGL
            if not egl.eglInitialize(self.display, None, None):
                return False
            
            # 配置EGL
            config_attribs = [
                egl.EGL_SURFACE_TYPE, egl.EGL_PBUFFER_BIT,
                egl.EGL_BLUE_SIZE, 8,
                egl.EGL_GREEN_SIZE, 8,
                egl.EGL_RED_SIZE, 8,
                egl.EGL_ALPHA_SIZE, 8,
                egl.EGL_RENDERABLE_TYPE, egl.EGL_OPENGL_BIT,
                egl.EGL_NONE
            ]
            
            configs = egl.eglChooseConfig(self.display, config_attribs, 1)
            if not configs:
                return False
            
            config = configs[0]
            
            # 创建上下文
            context_attribs = [egl.EGL_CONTEXT_MAJOR_VERSION, 3, egl.EGL_CONTEXT_MINOR_VERSION, 3, egl.EGL_NONE]
            self.context = egl.eglCreateContext(self.display, config, egl.EGL_NO_CONTEXT, context_attribs)
            if self.context == egl.EGL_NO_CONTEXT:
                return False
            
            # 创建离屏表面
            surface_attribs = [
                egl.EGL_WIDTH, self.width,
                egl.EGL_HEIGHT, self.height,
                egl.EGL_NONE
            ]
            self.surface = egl.eglCreatePbufferSurface(self.display, config, surface_attribs)
            if self.surface == egl.EGL_NO_SURFACE:
                return False
            
            # 激活上下文
            if not egl.eglMakeCurrent(self.display, self.surface, self.surface, self.context):
                return False
            
            # 初始化OpenGL状态
            self._init_opengl_state()
            
            self.is_initialized = True
            print(f"[GPU渲染] EGL上下文初始化成功: {self.width}x{self.height}")
            return True
            
        except Exception as e:
            print(f"[GPU渲染] EGL上下文初始化失败: {e}")
            return False
    
    def _init_fallback_context(self) -> bool:
        """初始化回退上下文"""
        # 这里可以实现其他上下文创建方法
        # 比如使用GLFW、SDL等
        print("[GPU渲染] 使用回退上下文创建方法")
        return False
    
    def _init_opengl_state(self):
        """初始化OpenGL状态"""
        # 设置视口
        gl.glViewport(0, 0, self.width, self.height)
        
        # 启用混合
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 创建帧缓冲
        self.framebuffer = gl.glGenFramebuffers(1)
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        
        # 创建颜色纹理
        self.color_texture = gl.glGenTextures(1)
        gl.glBindTexture(GL_TEXTURE_2D, self.color_texture)
        gl.glTexImage2D(GL_TEXTURE_2D, 0, gl.GL_RGBA8, self.width, self.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        # 附加到帧缓冲
        gl.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.color_texture, 0)
        
        # 检查帧缓冲完整性
        if gl.glCheckFramebufferStatus(GL_FRAMEBUFFER) != gl.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("帧缓冲不完整")
    
    def cleanup(self):
        """清理GPU上下文"""
        try:
            if self.is_initialized and EGL_AVAILABLE:
                if self.color_texture:
                    gl.glDeleteTextures([self.color_texture])
                if self.framebuffer:
                    gl.glDeleteFramebuffers([self.framebuffer])
                
                egl.eglMakeCurrent(self.display, egl.EGL_NO_SURFACE, egl.EGL_NO_SURFACE, egl.EGL_NO_CONTEXT)
                if self.surface:
                    egl.eglDestroySurface(self.display, self.surface)
                if self.context:
                    egl.eglDestroyContext(self.display, self.context)
                if self.display:
                    egl.eglTerminate(self.display)
            
            self.is_initialized = False
            print("[GPU渲染] GPU上下文已清理")
            
        except Exception as e:
            print(f"[GPU渲染] GPU上下文清理失败: {e}")


class GPURenderer:
    """GPU加速渲染器"""
    
    def __init__(self, config: GPURenderConfig = None):
        self.config = config or GPURenderConfig()
        self.context = None
        self.shader_manager = None
        self.is_available = False
        self.lock = threading.Lock()
        
        # 性能统计
        self.render_count = 0
        self.total_render_time = 0.0
        self.gpu_render_count = 0
        self.cpu_fallback_count = 0
        
        print(f"[GPU渲染] GPU渲染器初始化，GPU启用: {self.config.enable_gpu}")
    
    def initialize(self, width: int, height: int) -> bool:
        """初始化GPU渲染器"""
        with self.lock:
            if not self.config.enable_gpu or not OPENGL_AVAILABLE:
                print("[GPU渲染] GPU渲染被禁用或OpenGL不可用")
                return False
            
            try:
                # 创建GPU上下文
                self.context = GPUContext(width, height)
                if not self.context.initialize():
                    print("[GPU渲染] GPU上下文初始化失败")
                    return False
                
                # 创建着色器管理器
                self.shader_manager = GPUShaderManager()
                
                self.is_available = True
                print(f"[GPU渲染] GPU渲染器初始化成功: {width}x{height}")
                return True
                
            except Exception as e:
                print(f"[GPU渲染] GPU渲染器初始化失败: {e}")
                self.is_available = False
                return False
    
    def is_gpu_available(self) -> bool:
        """检查GPU是否可用"""
        return self.is_available and self.context and self.context.is_initialized
    
    def render_composition_gpu(self, layers: List[Any], canvas_width: int, canvas_height: int) -> Optional[Image.Image]:
        """使用GPU渲染图层组合"""
        if not self.is_gpu_available():
            return None
        
        start_time = time.time()
        
        try:
            with self.lock:
                # 确保上下文尺寸正确
                if (self.context.width != canvas_width or 
                    self.context.height != canvas_height):
                    # 重新初始化上下文
                    self.context.cleanup()
                    self.context = GPUContext(canvas_width, canvas_height)
                    if not self.context.initialize():
                        return None
                
                # 清空帧缓冲
                gl.glBindFramebuffer(GL_FRAMEBUFFER, self.context.framebuffer)
                gl.glClear(GL_COLOR_BUFFER_BIT)
                
                # 渲染每个图层
                for layer in layers:
                    if not layer.visible:
                        continue
                    
                    # 获取图层图像
                    layer_image = self._get_layer_image(layer)
                    if layer_image is None:
                        continue
                    
                    # 渲染图层到GPU
                    self._render_layer_gpu(layer, layer_image)
                
                # 读取渲染结果
                result_image = self._read_framebuffer(canvas_width, canvas_height)
                
                # 更新统计
                render_time = time.time() - start_time
                self.render_count += 1
                self.total_render_time += render_time
                self.gpu_render_count += 1
                
                print(f"[GPU渲染] GPU渲染完成: {render_time:.3f}秒")
                return result_image
                
        except Exception as e:
            print(f"[GPU渲染] GPU渲染失败: {e}")
            self.cpu_fallback_count += 1
            return None
    
    def _get_layer_image(self, layer) -> Optional[Image.Image]:
        """获取图层图像"""
        try:
            # 检查是否是文字图层
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                return layer.render_text()
            
            # 普通图层
            # 🔧 关键修复：禁用GPU渲染器缓存图像使用，避免重复图片问题
            # if hasattr(layer, 'cached_image') and layer.cached_image is not None:
            #     return layer.cached_image
            elif hasattr(layer, 'get_random_image'):
                return layer.get_random_image()
            
            return None
            
        except Exception as e:
            print(f"[GPU渲染] 获取图层图像失败: {e}")
            return None
    
    def _render_layer_gpu(self, layer, layer_image: Image.Image):
        """在GPU上渲染单个图层"""
        try:
            # 将PIL图像转换为OpenGL纹理
            texture_id = self._create_texture_from_image(layer_image)
            
            # 设置变换矩阵
            transform_matrix = self._create_transform_matrix(layer)
            
            # 选择着色器程序
            if hasattr(layer, 'corner_radius') and layer.corner_radius > 0:
                program = self.shader_manager.get_program("corner_radius")
                gl.glUseProgram(program)
                gl.glUniform1f(gl.glGetUniformLocation(program, "cornerRadius"), layer.corner_radius)
                gl.glUniform2f(gl.glGetUniformLocation(program, "textureSize"), layer_image.width, layer_image.height)
            else:
                program = self.shader_manager.get_program("basic")
                gl.glUseProgram(program)
            
            # 设置uniform变量
            gl.glUniform1f(gl.glGetUniformLocation(program, "opacity"), layer.opacity)
            gl.glUniformMatrix4fv(gl.glGetUniformLocation(program, "transform"), 1, gl.GL_FALSE, transform_matrix)
            
            # 绑定纹理
            gl.glBindTexture(GL_TEXTURE_2D, texture_id)
            
            # 渲染四边形
            self._render_quad()
            
            # 清理纹理
            gl.glDeleteTextures([texture_id])
            
        except Exception as e:
            print(f"[GPU渲染] 图层GPU渲染失败: {e}")
    
    def _create_texture_from_image(self, image: Image.Image) -> int:
        """从PIL图像创建OpenGL纹理"""
        # 确保图像是RGBA格式
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 获取图像数据
        image_data = np.array(image)
        
        # 创建纹理
        texture_id = gl.glGenTextures(1)
        gl.glBindTexture(GL_TEXTURE_2D, texture_id)
        
        # 上传纹理数据
        gl.glTexImage2D(GL_TEXTURE_2D, 0, gl.GL_RGBA8, image.width, image.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
        
        # 设置纹理参数
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        return texture_id
    
    def _create_transform_matrix(self, layer) -> np.ndarray:
        """创建图层变换矩阵"""
        # 简化的变换矩阵（正交投影）
        # 这里可以根据需要添加更复杂的变换
        matrix = np.eye(4, dtype=np.float32)
        
        # 位置变换
        if hasattr(layer, 'x') and hasattr(layer, 'y'):
            # 转换为OpenGL坐标系
            x = (layer.x / self.context.width) * 2.0 - 1.0
            y = 1.0 - (layer.y / self.context.height) * 2.0
            matrix[3, 0] = x
            matrix[3, 1] = y
        
        return matrix
    
    def _render_quad(self):
        """渲染四边形"""
        try:
            # 创建顶点数据 (位置 + 纹理坐标)
            vertices = np.array([
                -1.0, -1.0, 0.0, 0.0, 1.0,  # 左下
                 1.0, -1.0, 0.0, 1.0, 1.0,  # 右下
                 1.0,  1.0, 0.0, 1.0, 0.0,  # 右上
                -1.0,  1.0, 0.0, 0.0, 0.0   # 左上
            ], dtype=np.float32)

            indices = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint32)

            # 创建并绑定VAO
            vao = gl.glGenVertexArrays(1)
            gl.glBindVertexArray(vao)

            # 创建VBO
            vbo = gl.glGenBuffers(1)
            gl.glBindBuffer(GL_ARRAY_BUFFER, vbo)
            gl.glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

            # 创建EBO
            ebo = gl.glGenBuffers(1)
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, ebo)
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

            # 设置顶点属性
            # 位置属性
            gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, 5 * 4, None)
            gl.glEnableVertexAttribArray(0)

            # 纹理坐标属性
            gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, gl.GL_FALSE, 5 * 4, gl.ctypes.c_void_p(3 * 4))
            gl.glEnableVertexAttribArray(1)

            # 绘制
            gl.glDrawElements(GL_TRIANGLES, 6, gl.GL_UNSIGNED_INT, None)

            # 清理
            gl.glDeleteBuffers([vbo, ebo])
            gl.glDeleteVertexArrays([vao])

        except Exception as e:
            print(f"[GPU渲染] 四边形渲染失败: {e}")
            # 回退到立即模式渲染
            self._render_quad_immediate()

    def _render_quad_immediate(self):
        """立即模式渲染四边形（回退方案）"""
        try:
            gl.glBegin(gl.GL_QUADS)
            gl.glTexCoord2f(0.0, 1.0); gl.glVertex3f(-1.0, -1.0, 0.0)  # 左下
            gl.glTexCoord2f(1.0, 1.0); gl.glVertex3f( 1.0, -1.0, 0.0)  # 右下
            gl.glTexCoord2f(1.0, 0.0); gl.glVertex3f( 1.0,  1.0, 0.0)  # 右上
            gl.glTexCoord2f(0.0, 0.0); gl.glVertex3f(-1.0,  1.0, 0.0)  # 左上
            gl.glEnd()
        except Exception as e:
            print(f"[GPU渲染] 立即模式渲染也失败: {e}")
    
    def _read_framebuffer(self, width: int, height: int) -> Image.Image:
        """从帧缓冲读取渲染结果"""
        # 读取像素数据
        gl.glBindFramebuffer(GL_FRAMEBUFFER, self.context.framebuffer)
        pixels = gl.glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE)
        
        # 转换为numpy数组
        image_array = np.frombuffer(pixels, dtype=np.uint8).reshape((height, width, 4))
        
        # 翻转Y轴（OpenGL坐标系与PIL不同）
        image_array = np.flipud(image_array)
        
        # 转换为PIL图像
        return Image.fromarray(image_array, 'RGBA')
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        avg_render_time = (self.total_render_time / self.render_count) if self.render_count > 0 else 0
        gpu_usage_rate = (self.gpu_render_count / self.render_count * 100) if self.render_count > 0 else 0
        
        return {
            'total_renders': self.render_count,
            'gpu_renders': self.gpu_render_count,
            'cpu_fallbacks': self.cpu_fallback_count,
            'avg_render_time': avg_render_time,
            'gpu_usage_rate': gpu_usage_rate,
            'total_render_time': self.total_render_time
        }
    
    def cleanup(self):
        """清理GPU渲染器"""
        with self.lock:
            if self.context:
                self.context.cleanup()
                self.context = None
            
            self.shader_manager = None
            self.is_available = False
            
            print("[GPU渲染] GPU渲染器已清理")


# 全局GPU渲染器实例
_gpu_renderer = None
_gpu_renderer_lock = threading.Lock()

def get_gpu_renderer(config: GPURenderConfig = None) -> GPURenderer:
    """获取全局GPU渲染器实例"""
    global _gpu_renderer
    
    with _gpu_renderer_lock:
        if _gpu_renderer is None:
            _gpu_renderer = GPURenderer(config)
        return _gpu_renderer

def cleanup_gpu_renderer():
    """清理全局GPU渲染器"""
    global _gpu_renderer
    
    with _gpu_renderer_lock:
        if _gpu_renderer is not None:
            _gpu_renderer.cleanup()
            _gpu_renderer = None
