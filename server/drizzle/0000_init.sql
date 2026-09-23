CREATE TABLE `kv` (
	`name` varchar(64) NOT NULL,
	`value` text NOT NULL,
	CONSTRAINT `kv_name` PRIMARY KEY(`name`)
);
--> statement-breakpoint
CREATE TABLE `pageviews` (
	`id` varchar(40) NOT NULL,
	`ts` bigint NOT NULL,
	`day` char(10) NOT NULL,
	`hour` bigint NOT NULL,
	`session` varchar(40) NOT NULL,
	`visitor` char(20) NOT NULL,
	`path` varchar(512) NOT NULL,
	`section` varchar(128) NOT NULL,
	`entry` boolean NOT NULL DEFAULT false,
	`referrer` varchar(100),
	`lang` varchar(8),
	`device` varchar(16),
	`browser` varchar(32),
	`os` varchar(32),
	`duration` int,
	CONSTRAINT `pageviews_id` PRIMARY KEY(`id`)
) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
--> statement-breakpoint
CREATE INDEX `pageviews_ts` ON `pageviews` (`ts`);--> statement-breakpoint
CREATE INDEX `pageviews_path_ts` ON `pageviews` (`path`,`ts`);--> statement-breakpoint
CREATE INDEX `pageviews_session` ON `pageviews` (`session`);