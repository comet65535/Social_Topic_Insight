@echo off
chcp 65001 >nul
set "project_path=G:\Desktop\智能应用系统课设\vue\word-cloud-visualization"

echo ==============================
echo 正在检查项目目录是否存在...
if not exist "%project_path%" (
    echo 错误：项目目录不存在！
    echo 目录路径：%project_path%
    pause
    exit /b 1
)

echo 项目目录存在，正在进入...
cd /d "%project_path%" || (
    echo 错误：无法进入项目目录！
    pause
    exit /b 1
)

echo 正在启动前端项目（npm run dev）...
echo 启动后请访问：http://127.0.0.1:5173/
echo ==============================
npm run dev

echo 项目已停止运行！
pause