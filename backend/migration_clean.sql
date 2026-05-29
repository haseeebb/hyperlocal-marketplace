-- Enable pgvector extension (required for VECTOR columns)
CREATE EXTENSION IF NOT EXISTS vector;

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 48b8fbd07e74

CREATE TYPE userrole AS ENUM ('buyer', 'seller', 'admin');

CREATE TABLE users (
    id UUID NOT NULL, 
    phone VARCHAR(20) NOT NULL, 
    name VARCHAR(100), 
    role userrole, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    UNIQUE (phone)
);

CREATE TYPE storecategory AS ENUM ('products', 'services', 'restaurant', 'hotel');

CREATE TABLE stores (
    id UUID NOT NULL, 
    owner_id UUID, 
    name VARCHAR(150) NOT NULL, 
    description TEXT, 
    category storecategory, 
    city VARCHAR(100), 
    lat NUMERIC(9, 6), 
    lng NUMERIC(9, 6), 
    whatsapp_number VARCHAR(20), 
    is_verified BOOLEAN, 
    is_active BOOLEAN, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE TABLE listings (
    id UUID NOT NULL, 
    store_id UUID, 
    title VARCHAR(200) NOT NULL, 
    description TEXT, 
    price NUMERIC(10, 2), 
    currency VARCHAR(10), 
    image_url TEXT, 
    image_embedding VECTOR(512), 
    is_available BOOLEAN, 
    delivery_available BOOLEAN, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(store_id) REFERENCES stores (id)
);

INSERT INTO alembic_version (version_num) VALUES ('48b8fbd07e74') RETURNING alembic_version.version_num;

-- Running upgrade 48b8fbd07e74 -> 12a9f09d3272

ALTER TABLE users ADD COLUMN hashed_password VARCHAR(255);

UPDATE alembic_version SET version_num='12a9f09d3272' WHERE alembic_version.version_num = '48b8fbd07e74';

-- Running upgrade 12a9f09d3272 -> c547746670d6

UPDATE alembic_version SET version_num='c547746670d6' WHERE alembic_version.version_num = '12a9f09d3272';

-- Running upgrade c547746670d6 -> 0fd672c28f85

ALTER TABLE users ADD COLUMN supabase_user_id VARCHAR(36);

ALTER TABLE users ADD CONSTRAINT uq_users_supabase_user_id UNIQUE (supabase_user_id);

CREATE TABLE reviews (
    id UUID NOT NULL, 
    listing_id UUID, 
    store_id UUID NOT NULL, 
    buyer_name VARCHAR(100) NOT NULL, 
    rating INTEGER NOT NULL, 
    comment TEXT, 
    created_at TIMESTAMP WITHOUT TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(listing_id) REFERENCES listings (id), 
    FOREIGN KEY(store_id) REFERENCES stores (id)
);

UPDATE alembic_version SET version_num='0fd672c28f85' WHERE alembic_version.version_num = 'c547746670d6';

COMMIT;


