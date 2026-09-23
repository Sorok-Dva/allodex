CREATE TABLE `talent_build_events` (
	`id` bigint AUTO_INCREMENT NOT NULL,
	`build` char(12) NOT NULL,
	`kind` varchar(12) NOT NULL,
	`ts` bigint NOT NULL,
	`day` char(10) NOT NULL,
	`visitor` char(20) NOT NULL,
	`lang` varchar(8),
	CONSTRAINT `talent_build_events_id` PRIMARY KEY(`id`),
	CONSTRAINT `talent_build_events_once` UNIQUE(`build`,`kind`,`day`,`visitor`)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
--> statement-breakpoint
CREATE TABLE `talent_builds` (
	`id` char(12) NOT NULL,
	`version` varchar(16) NOT NULL,
	`class` varchar(32) NOT NULL,
	`b` varchar(255),
	`b2` varchar(255),
	`player_id` int,
	`generations` int NOT NULL DEFAULT 0,
	`shares` int NOT NULL DEFAULT 0,
	`views` int NOT NULL DEFAULT 0,
	`first_ts` bigint NOT NULL,
	`last_ts` bigint NOT NULL,
	CONSTRAINT `talent_builds_id` PRIMARY KEY(`id`)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
--> statement-breakpoint
CREATE INDEX `talent_build_events_ts` ON `talent_build_events` (`ts`);--> statement-breakpoint
CREATE INDEX `talent_builds_class` ON `talent_builds` (`version`,`class`);--> statement-breakpoint
CREATE INDEX `talent_builds_player` ON `talent_builds` (`player_id`);--> statement-breakpoint
CREATE INDEX `talent_builds_first` ON `talent_builds` (`first_ts`);