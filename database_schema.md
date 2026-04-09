erDiagram
    USER ||--o{ USER_EXPLORED_TILES : "explores"
    TILE ||--o{ USER_EXPLORED_TILES : "explored by"
    TILE ||--o{ POI : "contains"
    TILE ||--o{ TILE_POST_PROCESSING_POIS : "has"
    POST_PROCESSING_POI ||--o{ TILE_POST_PROCESSING_POIS : "linked to"

    USER {
        int id PK
        string username UK
        string hashed_password
    }

    TILE {
        string h3_cell PK
        string tile_type
    }

    POI {
        int id PK
        string h3_cell FK
        int osm_id
        string name
        float lat
        float lon
        int elevation
    }

    POST_PROCESSING_POI {
        int id PK
        int osm_id UK
        string name
        string tile_type
    }

    USER_EXPLORED_TILES {
        int user_id PK, FK
        string tile_h3_cell PK, FK
    }

    TILE_POST_PROCESSING_POIS {
        string tile_h3_cell PK, FK
        int post_processing_poi_id PK, FK
    }
