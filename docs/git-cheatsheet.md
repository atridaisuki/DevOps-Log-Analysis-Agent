# Git 常用命令速查

## 日常流程

```bash
git status              # 看当前改了什么
git add .               # 暂存所有改动（或 git add 文件名）
git commit -m "消息"     # 提交
git push                # 推到远程
git pull                # 拉取远程最新
git log --oneline -10   # 看最近 10 条提交
```

## 第一次推送

```bash
git init                                        # 初始化仓库
git remote add origin https://github.com/xxx.git # 关联远程（一次性）
git add .
git commit -m "init"
git push -u origin master                        # -u 设置默认追踪，以后直接 git push
```

## 团队协作流程

```bash
# 1. 从 main 拉最新，开功能分支
git checkout main
git pull
git checkout -b feature/add-login

# 2. 开发，提交，推分支
git add .
git commit -m "add login"
git push -u origin feature/add-login

# 3. GitHub 上创建 Pull Request → code review → 合并
```

## 合并别人的更新

```bash
# merge（保留分叉历史，公司常用）
git checkout feature/xxx
git merge main

# rebase（线性历史，个人项目用）
git checkout feature/xxx
git rebase main
```

区别：
```
merge:   A - B - C - - - M    有分叉，能看到分支从哪来
              \       /
               D - E

rebase:  A - B - C - D' - E'  一条线，历史干净
```

## 解决冲突

冲突时文件里会出现：
```
<<<<<<< HEAD
你的代码
=======
别人的代码
>>>>>>> main
```

手动选择保留哪个，然后：
```bash
git add 冲突文件
git commit -m "resolve conflict"
```

## 撤销操作

```bash
git reset --soft HEAD~1    # 撤销提交，改动留在暂存区
git reset --hard HEAD~1    # 撤销提交，改动全丢（危险）
git revert HEAD            # 新建一个提交来反做上一次（安全）
```

## 偶尔用的

```bash
git diff                # 看未暂存的改动
git diff --staged       # 看已暂存未提交的
git branch              # 看当前分支
git stash               # 临时存起改动
git stash pop           # 恢复存起的改动
```
