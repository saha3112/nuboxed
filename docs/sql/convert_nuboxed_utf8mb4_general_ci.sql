-- Nuboxed / phpMyAdmin charset setup
-- Run while connected to the nuboxed database.
-- This keeps existing data and converts every table/text column consistently.

SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;
ALTER DATABASE `nuboxed` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
SET FOREIGN_KEY_CHECKS = 0;
SET SESSION group_concat_max_len = 1048576;

DROP PROCEDURE IF EXISTS `nuboxed_convert_utf8mb4_general_ci`;
DELIMITER //
CREATE PROCEDURE `nuboxed_convert_utf8mb4_general_ci`()
BEGIN
    DECLARE finished INT DEFAULT 0;
    DECLARE table_name_value VARCHAR(255);
    DECLARE table_cursor CURSOR FOR
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'nuboxed'
          AND TABLE_TYPE = 'BASE TABLE';
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET finished = 1;

    OPEN table_cursor;
    convert_loop: LOOP
        FETCH table_cursor INTO table_name_value;
        IF finished = 1 THEN
            LEAVE convert_loop;
        END IF;
        SET @convert_sql = CONCAT(
            'ALTER TABLE `nuboxed`.`',
            REPLACE(table_name_value, '`', '``'),
            '` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci'
        );
        PREPARE convert_statement FROM @convert_sql;
        EXECUTE convert_statement;
        DEALLOCATE PREPARE convert_statement;
    END LOOP;
    CLOSE table_cursor;
END//
DELIMITER ;

CALL `nuboxed_convert_utf8mb4_general_ci`();
DROP PROCEDURE `nuboxed_convert_utf8mb4_general_ci`;
SET FOREIGN_KEY_CHECKS = 1;

-- Verify after import:
SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'nuboxed';
