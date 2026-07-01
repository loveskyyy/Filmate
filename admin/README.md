# Filmate Admin

Filmate 管理后台前端

## 快速开始

```bash
cd admin
pnpm install
pnpm dev
```

访问 http://localhost:3001

## 功能

- **用户管理** - 添加、编辑、删除用户（支持积分管理）
- **角色权限** - admin / 普通用户
- **登录控制** - 非管理员用户无法登录
- **系统配置** - 站点名称、最大项目数等

## 数据流

```
Admin Frontend (:3001) → Filmate Server (:1241)
```

## 初始化管理员

```bash
# 在 Filmate 项目根目录执行
python scripts/init_admin.py
```

默认管理员账号:
- 用户名: `admin`
- 密码: `admin123`
