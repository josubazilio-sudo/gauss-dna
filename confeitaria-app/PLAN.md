# Confeitaria App - Plano de Desenvolvimento

## Arquitetura
- **Monorepo** com Turborepo + pnpm
- **apps/web** - Next.js (App Router, Tailwind, Prisma) - site web
- **apps/mobile** - React Native (Expo, NativeWind) - app mobile
- **packages/shared** - Tipos, schemas Zod, utils compartilhados
- **packages/ui** - Componentes UI compartilhados

## Funcionalidades
1. **Catálogo** - Bolos/doces com fotos, descrição, preço, categorias
2. **Pedidos** - Carrinho de compras, checkout, histórico
3. **Delivery** - Endereço, taxa de entrega, formas de pagamento
4. **Rede Social** - Perfil da confeitaria, postar fotos, comentários
5. **Agenda** - Calendário de datas disponíveis, agendamento

## Banco de Dados (Prisma + PostgreSQL)
- User, Product, Category, Order, OrderItem, Cart, CartItem
- Appointment, Schedule, Post, Comment, Address, PaymentMethod

## Etapas
1. Scaffolding monorepo + configuração
2. Schema do banco + seed
3. API (categorias, produtos, autenticação)
4. Web Frontend (catálogo, pedidos, agenda)
5. Mobile Frontend (expo, mesma API)
6. Deploy
