-- ============================================================
-- 《AI学习助手》数据库初始化脚本
-- 用途：创建开发库（ai_quiz）与测试库（ai_quiz_test）
-- 使用：在 Navicat 中连接 MySQL 后，新建查询并执行本脚本
-- 说明：开发阶段直接使用 root 账号连接即可，无需额外建用户
-- ============================================================

CREATE DATABASE IF NOT EXISTS `ai_quiz`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

CREATE DATABASE IF NOT EXISTS `ai_quiz_test`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

-- 查看结果
SHOW DATABASES LIKE 'ai_quiz%';
