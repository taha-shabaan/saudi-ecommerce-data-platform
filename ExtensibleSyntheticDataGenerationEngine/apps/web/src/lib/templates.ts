import { EntityDefinition } from './types';

export interface SchemaTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  entities: EntityDefinition[];
}

export const STARTER_TEMPLATES: SchemaTemplate[] = [
  {
    id: 'ecommerce',
    name: 'E-Commerce Platform',
    description: 'Relational model for customers, products, orders, and line items.',
    icon: '🛒',
    entities: [
      {
        name: 'customers',
        record_count: 25,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'full_name', type: 'full_name', is_primary_key: false, nullable: false },
          { name: 'email', type: 'email', is_primary_key: false, nullable: false },
          { name: 'phone', type: 'phone', is_primary_key: false, nullable: true },
          { name: 'street_address', type: 'street_address', is_primary_key: false, nullable: false },
          { name: 'city', type: 'city', is_primary_key: false, nullable: false },
          { name: 'country', type: 'country', is_primary_key: false, nullable: false }
        ]
      },
      {
        name: 'products',
        record_count: 15,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'sku', type: 'uuid', is_primary_key: false, nullable: false },
          { name: 'title', type: 'categorical', params: { choices: ['Ergonomic Chair', 'UltraWide Monitor', 'Mechanical Keyboard', 'USB-C Docking Station', 'Noise-Canceling Mic'] }, is_primary_key: false, nullable: false },
          { name: 'category', type: 'categorical', params: { choices: ['Electronics', 'Furniture', 'Accessories', 'Peripherals'] }, is_primary_key: false, nullable: false },
          { name: 'price_cents', type: 'numeric_range', params: { min: 1999, max: 89900 }, is_primary_key: false, nullable: false }
        ]
      },
      {
        name: 'orders',
        record_count: 50,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'customer_id', type: 'foreign_key', fk_target: 'customers.id', is_primary_key: false, nullable: false },
          { name: 'order_date', type: 'date_time', is_primary_key: false, nullable: false },
          { name: 'status', type: 'categorical', params: { choices: ['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED'] }, is_primary_key: false, nullable: false },
          { name: 'total_cents', type: 'numeric_range', params: { min: 2500, max: 150000 }, is_primary_key: false, nullable: false }
        ]
      },
      {
        name: 'order_items',
        record_count: 100,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'order_id', type: 'foreign_key', fk_target: 'orders.id', is_primary_key: false, nullable: false },
          { name: 'product_id', type: 'foreign_key', fk_target: 'products.id', is_primary_key: false, nullable: false },
          { name: 'quantity', type: 'numeric_range', params: { min: 1, max: 5 }, is_primary_key: false, nullable: false },
          { name: 'unit_price_cents', type: 'numeric_range', params: { min: 1999, max: 89900 }, is_primary_key: false, nullable: false }
        ]
      }
    ]
  },
  {
    id: 'b2b-saas',
    name: 'B2B SaaS Multi-Tenant',
    description: 'Tenants, members, subscription plans, and generated monthly invoices.',
    icon: '🏢',
    entities: [
      {
        name: 'tenants',
        record_count: 10,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'tenant_uuid', type: 'uuid', is_primary_key: false, nullable: false },
          { name: 'company_name', type: 'text', is_primary_key: false, nullable: false },
          { name: 'domain', type: 'email', is_primary_key: false, nullable: false },
          { name: 'is_active', type: 'boolean', params: { true_probability: 0.9 }, is_primary_key: false, nullable: false }
        ]
      },
      {
        name: 'members',
        record_count: 40,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'tenant_id', type: 'foreign_key', fk_target: 'tenants.id', is_primary_key: false, nullable: false },
          { name: 'full_name', type: 'full_name', is_primary_key: false, nullable: false },
          { name: 'email', type: 'email', is_primary_key: false, nullable: false },
          { name: 'role', type: 'categorical', params: { choices: ['OWNER', 'ADMIN', 'MEMBER', 'BILLING'] }, is_primary_key: false, nullable: false }
        ]
      },
      {
        name: 'invoices',
        record_count: 60,
        attributes: [
          { name: 'id', type: 'autoincrement', is_primary_key: true, nullable: false },
          { name: 'tenant_id', type: 'foreign_key', fk_target: 'tenants.id', is_primary_key: false, nullable: false },
          { name: 'invoice_date', type: 'date_time', is_primary_key: false, nullable: false },
          { name: 'amount_cents', type: 'numeric_range', params: { min: 4900, max: 49900 }, is_primary_key: false, nullable: false },
          { name: 'paid_status', type: 'categorical', params: { choices: ['PAID', 'OVERDUE', 'REFUNDED'] }, is_primary_key: false, nullable: false }
        ]
      }
    ]
  }
];

export const AVAILABLE_COUNTRIES = [
  { code: 'ar_EG', country: 'Egypt', flag: '🇪🇬' },
  { code: 'en_US', country: 'United States', flag: '🇺🇸' },
  { code: 'de_DE', country: 'Germany', flag: '🇩🇪' },
  { code: 'fr_FR', country: 'France', flag: '🇫🇷' },
  { code: 'ar_SA', country: 'Saudi Arabia', flag: '🇸🇦' }
];
