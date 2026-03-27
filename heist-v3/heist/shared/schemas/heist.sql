--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Ubuntu 16.9-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.9 (Ubuntu 16.9-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: commands; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA commands;


ALTER SCHEMA commands OWNER TO postgres;

--
-- Name: disboard; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA disboard;


ALTER SCHEMA disboard OWNER TO postgres;

--
-- Name: family; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA family;


ALTER SCHEMA family OWNER TO postgres;

--
-- Name: fortnite; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA fortnite;


ALTER SCHEMA fortnite OWNER TO postgres;

--
-- Name: guild; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA guild;


ALTER SCHEMA guild OWNER TO postgres;

--
-- Name: jail; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA jail;


ALTER SCHEMA jail OWNER TO postgres;

--
-- Name: joindm; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA joindm;


ALTER SCHEMA joindm OWNER TO postgres;

--
-- Name: lastfm; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA lastfm;


ALTER SCHEMA lastfm OWNER TO postgres;

--
-- Name: level; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA level;


ALTER SCHEMA level OWNER TO postgres;

--
-- Name: pingonjoin; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA pingonjoin;


ALTER SCHEMA pingonjoin OWNER TO postgres;

--
-- Name: snipe; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA snipe;


ALTER SCHEMA snipe OWNER TO postgres;

--
-- Name: ticket; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA ticket;


ALTER SCHEMA ticket OWNER TO postgres;

--
-- Name: timer; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA timer;


ALTER SCHEMA timer OWNER TO postgres;

--
-- Name: user; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA "user";


ALTER SCHEMA "user" OWNER TO postgres;

--
-- Name: voicemaster; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA voicemaster;


ALTER SCHEMA voicemaster OWNER TO postgres;

--
-- Name: autopfp; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA autopfp;


ALTER SCHEMA autopfp OWNER TO postgres;

--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: disabled; Type: TABLE; Schema: commands; Owner: postgres
--

CREATE TABLE commands.disabled (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    command text NOT NULL
);


ALTER TABLE commands.disabled OWNER TO postgres;

--
-- Name: ignore; Type: TABLE; Schema: commands; Owner: postgres
--

CREATE TABLE commands.ignore (
    guild_id bigint NOT NULL,
    target_id bigint NOT NULL
);


ALTER TABLE commands.ignore OWNER TO postgres;

--
-- Name: restricted; Type: TABLE; Schema: commands; Owner: postgres
--

CREATE TABLE commands.restricted (
    guild_id bigint NOT NULL,
    role_id bigint NOT NULL,
    command text NOT NULL
);


ALTER TABLE commands.restricted OWNER TO postgres;

--
-- Name: usage; Type: TABLE; Schema: commands; Owner: postgres
--

CREATE TABLE commands.usage (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    user_id bigint NOT NULL,
    command text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE commands.usage OWNER TO postgres;

--
-- Name: bump; Type: TABLE; Schema: disboard; Owner: postgres
--

CREATE TABLE disboard.bump (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    bumped_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE disboard.bump OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: disboard; Owner: postgres
--

CREATE TABLE disboard.config (
    guild_id bigint NOT NULL,
    status boolean DEFAULT true NOT NULL,
    channel_id bigint,
    last_channel_id bigint,
    last_user_id bigint,
    message text,
    thank_message text,
    next_bump timestamp with time zone
);


ALTER TABLE disboard.config OWNER TO postgres;

--
-- Name: members; Type: TABLE; Schema: family; Owner: postgres
--

CREATE TABLE family.members (
    user_id bigint NOT NULL,
    related_id bigint NOT NULL,
    relationship text
);


ALTER TABLE family.members OWNER TO postgres;

--
-- Name: reminder; Type: TABLE; Schema: fortnite; Owner: postgres
--

CREATE TABLE fortnite.reminder (
    user_id bigint NOT NULL,
    item_id text NOT NULL,
    item_name text NOT NULL,
    item_type text NOT NULL
);


ALTER TABLE fortnite.reminder OWNER TO postgres;

--
-- Name: rotation; Type: TABLE; Schema: fortnite; Owner: postgres
--

CREATE TABLE fortnite.rotation (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message text
);


ALTER TABLE fortnite.rotation OWNER TO postgres;

--
-- Name: settings; Type: TABLE; Schema: guild; Owner: postgres
--

CREATE TABLE guild.settings (
    guild_id bigint NOT NULL,
    config jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE guild.settings OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: jail; Owner: postgres
--

CREATE TABLE jail.config (
    guild_id bigint NOT NULL,
    channel_id bigint,
    jail_role_id bigint,
    message text
);


ALTER TABLE jail.config OWNER TO postgres;

--
-- Name: restore_roles; Type: TABLE; Schema: jail; Owner: postgres
--

CREATE TABLE jail.restore_roles (
    user_id bigint NOT NULL,
    guild_id bigint NOT NULL,
    roles jsonb
);


ALTER TABLE jail.restore_roles OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: jail; Owner: postgres
--

CREATE TABLE jail.users (
    user_id bigint NOT NULL,
    guild_id bigint NOT NULL,
    start_time timestamp without time zone
);


ALTER TABLE jail.users OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: joindm; Owner: postgres
--

CREATE TABLE joindm.config (
    guild_id bigint NOT NULL,
    message text,
    enabled boolean DEFAULT false
);


ALTER TABLE joindm.config OWNER TO postgres;

--
-- Name: albums; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.albums (
    user_id bigint NOT NULL,
    username text NOT NULL,
    artist public.citext NOT NULL,
    album public.citext NOT NULL,
    plays bigint NOT NULL
);


ALTER TABLE lastfm.albums OWNER TO postgres;

--
-- Name: artists; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.artists (
    user_id bigint NOT NULL,
    username text NOT NULL,
    artist public.citext NOT NULL,
    plays bigint NOT NULL
);


ALTER TABLE lastfm.artists OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.config (
    user_id bigint NOT NULL,
    username public.citext NOT NULL,
    color bigint,
    command text,
    reactions text[] DEFAULT '{}'::text[] NOT NULL,
    embed_mode text DEFAULT 'default'::text NOT NULL,
    last_indexed timestamp with time zone DEFAULT now() NOT NULL,
    access_token text,
    web_authentication boolean DEFAULT false
);


ALTER TABLE lastfm.config OWNER TO postgres;

--
-- Name: crown_updates; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.crown_updates (
    guild_id bigint NOT NULL,
    last_update timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE lastfm.crown_updates OWNER TO postgres;

--
-- Name: crowns; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.crowns (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    artist public.citext NOT NULL,
    claimed_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE lastfm.crowns OWNER TO postgres;

--
-- Name: hidden; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.hidden (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL
);


ALTER TABLE lastfm.hidden OWNER TO postgres;

--
-- Name: tracks; Type: TABLE; Schema: lastfm; Owner: postgres
--

CREATE TABLE lastfm.tracks (
    user_id bigint NOT NULL,
    username text NOT NULL,
    artist public.citext NOT NULL,
    track public.citext NOT NULL,
    plays bigint NOT NULL
);


ALTER TABLE lastfm.tracks OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: level; Owner: postgres
--

CREATE TABLE level.config (
    guild_id bigint NOT NULL,
    status boolean DEFAULT true NOT NULL,
    cooldown integer DEFAULT 60 NOT NULL,
    max_level integer DEFAULT 0 NOT NULL,
    stack_roles boolean DEFAULT true NOT NULL,
    formula_multiplier double precision DEFAULT 1 NOT NULL,
    xp_multiplier double precision DEFAULT 1 NOT NULL,
    xp_min integer DEFAULT 15 NOT NULL,
    xp_max integer DEFAULT 40 NOT NULL,
    effort_status boolean DEFAULT false NOT NULL,
    effort_text bigint DEFAULT 25 NOT NULL,
    effort_image bigint DEFAULT 3 NOT NULL,
    effort_booster bigint DEFAULT 10 NOT NULL
);


ALTER TABLE level.config OWNER TO postgres;

--
-- Name: member; Type: TABLE; Schema: level; Owner: postgres
--

CREATE TABLE level.member (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    xp integer DEFAULT 0 NOT NULL,
    level integer DEFAULT 0 NOT NULL,
    total_xp integer DEFAULT 0 NOT NULL,
    last_message timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE level.member OWNER TO postgres;

--
-- Name: notification; Type: TABLE; Schema: level; Owner: postgres
--

CREATE TABLE level.notification (
    guild_id bigint NOT NULL,
    channel_id bigint,
    dm boolean DEFAULT false NOT NULL,
    template text
);


ALTER TABLE level.notification OWNER TO postgres;

--
-- Name: role; Type: TABLE; Schema: level; Owner: postgres
--

CREATE TABLE level.role (
    guild_id bigint NOT NULL,
    role_id bigint NOT NULL,
    level integer NOT NULL
);


ALTER TABLE level.role OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: pingonjoin; Owner: postgres
--

CREATE TABLE pingonjoin.config (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    delete_ping boolean DEFAULT false,
    delete_after integer
);


ALTER TABLE pingonjoin.config OWNER TO postgres;

--
-- Name: afk; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.afk (
    user_id bigint NOT NULL,
    status text DEFAULT 'AFK'::text NOT NULL,
    left_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.afk OWNER TO postgres;

--
-- Name: afk_mentions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.afk_mentions (
    afk_user_id bigint NOT NULL,
    mentioner_id bigint NOT NULL,
    message_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    guild_id bigint,
    "timestamp" timestamp with time zone DEFAULT now()
);


ALTER TABLE public.afk_mentions OWNER TO postgres;

--
-- Name: aliases; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.aliases (
    guild_id bigint NOT NULL,
    name text NOT NULL,
    invoke text NOT NULL,
    command text NOT NULL
);


ALTER TABLE public.aliases OWNER TO postgres;

--
-- Name: ancfg; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ancfg (
    guild_id bigint,
    module text,
    punishment text,
    threshold integer
);


ALTER TABLE public.ancfg OWNER TO postgres;

--
-- Name: antinuke2; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antinuke2 (
    guild_id bigint NOT NULL,
    whitelist bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    admins bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    botadd jsonb DEFAULT '{}'::jsonb NOT NULL,
    webhook jsonb DEFAULT '{}'::jsonb NOT NULL,
    emoji jsonb DEFAULT '{}'::jsonb NOT NULL,
    ban jsonb DEFAULT '{}'::jsonb NOT NULL,
    kick jsonb DEFAULT '{}'::jsonb NOT NULL,
    channel jsonb DEFAULT '{}'::jsonb NOT NULL,
    role jsonb DEFAULT '{}'::jsonb NOT NULL,
    permissions jsonb[] DEFAULT '{}'::jsonb[] NOT NULL,
    massmention jsonb DEFAULT '{"status": false, "threshold": 5, "punishment": "kick"}'::jsonb,
    roleperms jsonb DEFAULT '{"status": false, "threshold": 1, "punishment": "ban"}'::jsonb,
    memberperms jsonb DEFAULT '{"status": false, "threshold": 1, "punishment": "ban"}'::jsonb,
    enabled boolean DEFAULT false
);


ALTER TABLE public.antinuke2 OWNER TO postgres;

--
-- Name: antinuke_admins; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antinuke_admins (
    guild_id bigint,
    user_id bigint
);


ALTER TABLE public.antinuke_admins OWNER TO postgres;

--
-- Name: antinuke_modules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antinuke_modules (
    guild_id bigint,
    module text,
    punishment text,
    threshold integer,
    toggled boolean DEFAULT false
);


ALTER TABLE public.antinuke_modules OWNER TO postgres;

--
-- Name: antinuke_toggle; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antinuke_toggle (
    guild_id bigint,
    logs bigint
);


ALTER TABLE public.antinuke_toggle OWNER TO postgres;

--
-- Name: antinuke_whitelist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antinuke_whitelist (
    guild_id bigint,
    user_id bigint
);


ALTER TABLE public.antinuke_whitelist OWNER TO postgres;

--
-- Name: antiraid; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.antiraid (
    guild_id bigint NOT NULL,
    locked boolean DEFAULT false NOT NULL,
    joins jsonb,
    mentions jsonb,
    avatar jsonb,
    browser jsonb,
    whitelist jsonb,
    no_avatar boolean DEFAULT false,
    no_avatar_punishment integer,
    new_accounts boolean DEFAULT false,
    new_account_punishment integer,
    new_account_threshold integer,
    lock_channels boolean DEFAULT false,
    punish boolean DEFAULT false,
    join_punishment integer,
    join_threshold integer,
    raid_status boolean DEFAULT false
);


ALTER TABLE public.antiraid OWNER TO postgres;

--
-- Name: auto_role; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auto_role (
    guild_id bigint NOT NULL,
    role_id bigint NOT NULL,
    action text NOT NULL,
    delay integer
);


ALTER TABLE public.auto_role OWNER TO postgres;

--
-- Name: blacklist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.blacklist (
    user_id bigint NOT NULL,
    information text,
    moderator bigint,
    date timestamp without time zone
);


ALTER TABLE public.blacklist OWNER TO postgres;

--
-- Name: blunt; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.blunt (
    guild_id bigint NOT NULL,
    user_id bigint,
    hits bigint DEFAULT 0,
    passes bigint DEFAULT 0,
    members jsonb[] DEFAULT '{}'::jsonb[]
);


ALTER TABLE public.blunt OWNER TO postgres;

--
-- Name: boost_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.boost_history (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    boost_count integer DEFAULT 0,
    first_boost_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_boost_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.boost_history OWNER TO postgres;

--
-- Name: boost_message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.boost_message (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    template text NOT NULL,
    delete_after integer
);


ALTER TABLE public.boost_message OWNER TO postgres;

--
-- Name: booster_role; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.booster_role (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    role_id bigint NOT NULL,
    shared boolean,
    multi_boost_enabled boolean DEFAULT false
);


ALTER TABLE public.booster_role OWNER TO postgres;

--
-- Name: boosters_lost; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.boosters_lost (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    lasted_for interval NOT NULL,
    ended_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.boosters_lost OWNER TO postgres;

--
-- Name: vesta_businesses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vesta_businesses (
    id integer NOT NULL,
    owner_id bigint NOT NULL,
    guild_id bigint NOT NULL,
    name character varying(100) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    thumbnail_url text,
    funds bigint DEFAULT 0
);


ALTER TABLE public.vesta_businesses OWNER TO postgres;

--
-- Name: businesses_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.businesses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.businesses_id_seq OWNER TO postgres;

--
-- Name: businesses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.businesses_id_seq OWNED BY public.vesta_businesses.id;


--
-- Name: counter; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.counter (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    option text NOT NULL,
    last_update timestamp with time zone DEFAULT now() NOT NULL,
    rate_limited_until timestamp with time zone
);


ALTER TABLE public.counter OWNER TO postgres;

--
-- Name: donators; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.donators (
    user_id bigint
);


ALTER TABLE public.donators OWNER TO postgres;

--
-- Name: fake_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.fake_permissions (
    guild_id bigint NOT NULL,
    role_id bigint NOT NULL,
    permission text NOT NULL
);


ALTER TABLE public.fake_permissions OWNER TO postgres;

--
-- Name: forcenick; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.forcenick (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    nickname character varying(32)
);


ALTER TABLE public.forcenick OWNER TO postgres;

--
-- Name: gallery; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gallery (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL
);


ALTER TABLE public.gallery OWNER TO postgres;

--
-- Name: giveaway; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.giveaway (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message_id bigint NOT NULL,
    prize text NOT NULL,
    emoji text NOT NULL,
    winners integer NOT NULL,
    ended boolean DEFAULT false NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    required_roles bigint[] DEFAULT '{}'::bigint[],
    bonus_roles jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE public.giveaway OWNER TO postgres;

--
-- Name: giveaway_entries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.giveaway_entries (
    message_id bigint NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.giveaway_entries OWNER TO postgres;

--
-- Name: giveaway_settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.giveaway_settings (
    guild_id bigint NOT NULL,
    bonus_roles jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.giveaway_settings OWNER TO postgres;

--
-- Name: gnames; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gnames (
    guild_id bigint NOT NULL,
    name text NOT NULL,
    changed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.gnames OWNER TO postgres;

--
-- Name: goodbye_message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.goodbye_message (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    template text NOT NULL,
    delete_after integer
);


ALTER TABLE public.goodbye_message OWNER TO postgres;

--
-- Name: guildblacklist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.guildblacklist (
    guild_id bigint NOT NULL,
    information text
);


ALTER TABLE public.guildblacklist OWNER TO postgres;

--
-- Name: hardban; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hardban (
    user_id bigint,
    guild_id bigint
);


ALTER TABLE public.hardban OWNER TO postgres;

--
-- Name: highlights; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.highlights (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    word text NOT NULL
);


ALTER TABLE public.highlights OWNER TO postgres;

--
-- Name: ignored_logging; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ignored_logging (
    guild_id bigint NOT NULL,
    target_id bigint NOT NULL
);


ALTER TABLE public.ignored_logging OWNER TO postgres;

--
-- Name: jail; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.jail (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    role_ids bigint[] NOT NULL
);


ALTER TABLE public.jail OWNER TO postgres;

--
-- Name: job_applications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.job_applications (
    id integer NOT NULL,
    user_id bigint NOT NULL,
    job_id integer NOT NULL,
    guild_id bigint NOT NULL,
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.job_applications OWNER TO postgres;

--
-- Name: job_applications_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.job_applications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.job_applications_id_seq OWNER TO postgres;

--
-- Name: job_applications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.job_applications_id_seq OWNED BY public.job_applications.id;


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.jobs (
    id integer NOT NULL,
    business_id integer NOT NULL,
    name character varying(50) NOT NULL,
    visibility character varying(7) NOT NULL,
    salary bigint DEFAULT 0,
    guild_id bigint NOT NULL,
    CONSTRAINT jobs_visibility_check CHECK (((visibility)::text = ANY (ARRAY[('public'::character varying)::text, ('private'::character varying)::text])))
);


ALTER TABLE public.jobs OWNER TO postgres;

--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.jobs_id_seq OWNER TO postgres;

--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: logging; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.logging (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    events text[] DEFAULT ARRAY[]::text[] NOT NULL,
    webhook_id bigint
);


ALTER TABLE public.logging OWNER TO postgres;

--
-- Name: logging_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.logging_history (
    id integer NOT NULL,
    guild_id bigint NOT NULL,
    channel_id bigint,
    event_type character varying(50) NOT NULL,
    content jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.logging_history OWNER TO postgres;

--
-- Name: logging_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.logging_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.logging_history_id_seq OWNER TO postgres;

--
-- Name: logging_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.logging_history_id_seq OWNED BY public.logging_history.id;


--
-- Name: marriages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.marriages (
    user_id bigint NOT NULL,
    partner_id bigint NOT NULL,
    married_at timestamp without time zone NOT NULL
);


ALTER TABLE public.marriages OWNER TO postgres;

--
-- Name: moderation; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.moderation (
    guild_id bigint NOT NULL,
    role_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    jail_id bigint NOT NULL,
    category_id bigint NOT NULL
);


ALTER TABLE public.moderation OWNER TO postgres;

--
-- Name: name_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.name_history (
    user_id bigint NOT NULL,
    username text NOT NULL,
    is_nickname boolean DEFAULT false NOT NULL,
    is_hidden boolean DEFAULT false NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.name_history OWNER TO postgres;

--
-- Name: pagination; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pagination (
    guild_id bigint NOT NULL,
    message_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    creator_id bigint NOT NULL,
    pages text[] NOT NULL,
    current_page bigint DEFAULT 0 NOT NULL
);


ALTER TABLE public.pagination OWNER TO postgres;

--
-- Name: pingonjoin; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pingonjoin (
    channel_id bigint,
    guild_id bigint
);


ALTER TABLE public.pingonjoin OWNER TO postgres;

--
-- Name: prefix; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.prefix (
    guild_id bigint NOT NULL,
    prefix character varying(7)
);


ALTER TABLE public.prefix OWNER TO postgres;

--
-- Name: properties; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.properties (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    description text NOT NULL,
    image_url text NOT NULL,
    earnings_per_hour bigint NOT NULL,
    cost bigint NOT NULL
);


ALTER TABLE public.properties OWNER TO postgres;

--
-- Name: properties_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.properties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.properties_id_seq OWNER TO postgres;

--
-- Name: properties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.properties_id_seq OWNED BY public.properties.id;


--
-- Name: publisher; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.publisher (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL
);


ALTER TABLE public.publisher OWNER TO postgres;

--
-- Name: reaction_role; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reaction_role (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message_id bigint NOT NULL,
    role_id bigint NOT NULL,
    emoji text NOT NULL
);


ALTER TABLE public.reaction_role OWNER TO postgres;

--
-- Name: reaction_trigger; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reaction_trigger (
    guild_id bigint NOT NULL,
    trigger public.citext NOT NULL,
    emoji text NOT NULL
);


ALTER TABLE public.reaction_trigger OWNER TO postgres;

--
-- Name: reskin; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reskin (
    user_id bigint,
    toggled boolean,
    username text,
    avatar text
);


ALTER TABLE public.reskin OWNER TO postgres;

--
-- Name: response_trigger; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.response_trigger (
    guild_id bigint NOT NULL,
    trigger public.citext NOT NULL,
    template text NOT NULL,
    strict boolean DEFAULT false NOT NULL,
    reply boolean DEFAULT false NOT NULL,
    delete boolean DEFAULT false NOT NULL,
    delete_after integer DEFAULT 0 NOT NULL,
    role_id bigint,
    sticker_id bigint
);


ALTER TABLE public.response_trigger OWNER TO postgres;

--
-- Name: role_restore; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.role_restore (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    roles bigint[] NOT NULL
);


ALTER TABLE public.role_restore OWNER TO postgres;

--
-- Name: roleplay; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.roleplay (
    user_id bigint NOT NULL,
    target_id bigint NOT NULL,
    category text NOT NULL,
    amount integer DEFAULT 1 NOT NULL
);


ALTER TABLE public.roleplay OWNER TO postgres;

--
-- Name: roleplay_enabled; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.roleplay_enabled (
    enabled boolean,
    guild_id bigint
);


ALTER TABLE public.roleplay_enabled OWNER TO postgres;

--
-- Name: settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.settings (
    guild_id bigint NOT NULL,
    prefixes text[] DEFAULT '{}'::text[] NOT NULL,
    reskin boolean DEFAULT false NOT NULL,
    reposter_prefix boolean DEFAULT true NOT NULL,
    reposter_delete boolean DEFAULT false NOT NULL,
    reposter_embed boolean DEFAULT true NOT NULL,
    transcription boolean DEFAULT false NOT NULL,
    welcome_removal boolean DEFAULT false NOT NULL,
    booster_role_base_id bigint,
    booster_role_include_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    lock_role_id bigint,
    lock_ignore_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    log_ignore_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    reassign_ignore_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    reassign_roles boolean DEFAULT false NOT NULL,
    invoke_kick text,
    invoke_ban text,
    invoke_unban text,
    invoke_timeout text,
    invoke_untimeout text,
    invoke_play text,
    play_panel boolean DEFAULT true NOT NULL,
    play_deletion boolean DEFAULT false NOT NULL,
    safesearch_level text DEFAULT 'strict'::text NOT NULL,
    author text,
    prefix character varying(7),
    dm_enabled boolean DEFAULT true,
    dm_ban text,
    dm_unban text,
    dm_kick text,
    dm_jail text,
    dm_unjail text,
    dm_mute text,
    dm_unmute text,
    dm_warn text,
    dm_timeout text,
    dm_untimeout text,
    dm_role_add text,
    dm_role_remove text,
    dm_antinuke_ban text,
    dm_antinuke_kick text,
    dm_antinuke_strip text,
    dm_antiraid_ban text,
    dm_antiraid_kick text,
    dm_antiraid_timeout text,
    dm_antiraid_strip text
);


ALTER TABLE public.settings OWNER TO postgres;

--
-- Name: shutup; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shutup (
    guild_id bigint,
    user_id bigint
);


ALTER TABLE public.shutup OWNER TO postgres;

--
-- Name: skullboard; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.skullboard (
    guild_id bigint NOT NULL,
    channel_id bigint,
    count integer DEFAULT 3 NOT NULL,
    emoji_id bigint,
    emoji_text text
);


ALTER TABLE public.skullboard OWNER TO postgres;

--
-- Name: skullboardmes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.skullboardmes (
    guild_id bigint NOT NULL,
    channel_skullboard_id bigint NOT NULL,
    channel_message_id bigint NOT NULL,
    message_skullboard_id bigint NOT NULL,
    message_id bigint NOT NULL
);


ALTER TABLE public.skullboardmes OWNER TO postgres;

--
-- Name: starboard; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.starboard (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    self_star boolean DEFAULT true NOT NULL,
    threshold integer DEFAULT 3 NOT NULL,
    emoji text DEFAULT '⭐'::text NOT NULL,
    color integer
);


ALTER TABLE public.starboard OWNER TO postgres;

--
-- Name: starboard_entry; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.starboard_entry (
    guild_id bigint NOT NULL,
    star_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message_id bigint NOT NULL,
    emoji text NOT NULL
);


ALTER TABLE public.starboard_entry OWNER TO postgres;

--
-- Name: sticky_message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sticky_message (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message_id bigint NOT NULL,
    template text NOT NULL
);


ALTER TABLE public.sticky_message OWNER TO postgres;

--
-- Name: tag_aliases; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tag_aliases (
    guild_id bigint NOT NULL,
    alias text NOT NULL,
    original text
);


ALTER TABLE public.tag_aliases OWNER TO postgres;

--
-- Name: tags; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tags (
    guild_id bigint NOT NULL,
    name text NOT NULL,
    owner_id bigint,
    template text,
    uses bigint DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    restricted_user bigint,
    restricted_role bigint
);


ALTER TABLE public.tags OWNER TO postgres;

--
-- Name: thread; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.thread (
    guild_id bigint NOT NULL,
    thread_id bigint NOT NULL
);


ALTER TABLE public.thread OWNER TO postgres;

--
-- Name: user_properties; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_properties (
    id integer NOT NULL,
    user_id bigint NOT NULL,
    property_id integer NOT NULL,
    last_collected timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_properties OWNER TO postgres;

--
-- Name: user_properties_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_properties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_properties_id_seq OWNER TO postgres;

--
-- Name: user_properties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_properties_id_seq OWNED BY public.user_properties.id;


--
-- Name: uwulock; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.uwulock (
    guild_id bigint,
    user_id bigint
);


ALTER TABLE public.uwulock OWNER TO postgres;

--
-- Name: vape; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vape (
    user_id bigint NOT NULL,
    flavor text,
    hits bigint DEFAULT 0 NOT NULL
);


ALTER TABLE public.vape OWNER TO postgres;

--
-- Name: vesta_economy; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vesta_economy (
    user_id bigint NOT NULL,
    wallet bigint DEFAULT 1000 NOT NULL,
    bank bigint DEFAULT 0 NOT NULL,
    daily timestamp without time zone NOT NULL,
    monthly timestamp without time zone NOT NULL,
    yearly timestamp without time zone NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    daily_streak integer DEFAULT 0,
    monthly_streak integer DEFAULT 0,
    yearly_streak integer DEFAULT 0,
    anonymous boolean DEFAULT false,
    last_stripped timestamp with time zone
);


ALTER TABLE public.vesta_economy OWNER TO postgres;

--
-- Name: voicemaster; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.voicemaster (
    guild_id bigint,
    voice_id bigint,
    text_id bigint,
    category_id bigint
);


ALTER TABLE public.voicemaster OWNER TO postgres;

--
-- Name: warns; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warns (
    user_id bigint NOT NULL,
    guild_id bigint NOT NULL,
    reason text NOT NULL,
    date timestamp with time zone NOT NULL
);


ALTER TABLE public.warns OWNER TO postgres;

--
-- Name: webhook; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.webhook (
    identifier text NOT NULL,
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    author_id bigint NOT NULL,
    webhook_id bigint NOT NULL
);


ALTER TABLE public.webhook OWNER TO postgres;

--
-- Name: welcome_message; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.welcome_message (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    template text NOT NULL,
    delete_after integer
);


ALTER TABLE public.welcome_message OWNER TO postgres;

--
-- Name: whitelist; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.whitelist (
    id integer NOT NULL,
    guild_id bigint NOT NULL,
    user_id bigint,
    status boolean DEFAULT false NOT NULL,
    action text DEFAULT 'kick'::text NOT NULL
);


ALTER TABLE public.whitelist OWNER TO postgres;

--
-- Name: whitelist_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.whitelist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.whitelist_id_seq OWNER TO postgres;

--
-- Name: whitelist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.whitelist_id_seq OWNED BY public.whitelist.id;


--
-- Name: workers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.workers (
    user_id bigint NOT NULL,
    job_id integer NOT NULL,
    last_worked timestamp without time zone,
    guild_id bigint NOT NULL
);


ALTER TABLE public.workers OWNER TO postgres;

--
-- Name: edits; Type: TABLE; Schema: snipe; Owner: postgres
--

CREATE TABLE snipe.edits (
    id integer NOT NULL,
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    user_id bigint NOT NULL,
    old_content text,
    new_content text,
    edited_at timestamp with time zone DEFAULT now(),
    old_stickers text,
    new_stickers text,
    old_attachments text,
    new_attachments text
);


ALTER TABLE snipe.edits OWNER TO postgres;

--
-- Name: edits_id_seq; Type: SEQUENCE; Schema: snipe; Owner: postgres
--

CREATE SEQUENCE snipe.edits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE snipe.edits_id_seq OWNER TO postgres;

--
-- Name: edits_id_seq; Type: SEQUENCE OWNED BY; Schema: snipe; Owner: postgres
--

ALTER SEQUENCE snipe.edits_id_seq OWNED BY snipe.edits.id;


--
-- Name: filter; Type: TABLE; Schema: snipe; Owner: postgres
--

CREATE TABLE snipe.filter (
    guild_id bigint NOT NULL,
    invites boolean DEFAULT false NOT NULL,
    links boolean DEFAULT false NOT NULL,
    words text[] DEFAULT '{}'::text[] NOT NULL
);


ALTER TABLE snipe.filter OWNER TO postgres;

--
-- Name: ignore; Type: TABLE; Schema: snipe; Owner: postgres
--

CREATE TABLE snipe.ignore (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL
);


ALTER TABLE snipe.ignore OWNER TO postgres;

--
-- Name: messages; Type: TABLE; Schema: snipe; Owner: postgres
--

CREATE TABLE snipe.messages (
    id integer NOT NULL,
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    user_id bigint NOT NULL,
    content text,
    deleted_at timestamp with time zone DEFAULT now(),
    stickers text,
    attachments text,
    files text
);


ALTER TABLE snipe.messages OWNER TO postgres;

--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: snipe; Owner: postgres
--

CREATE SEQUENCE snipe.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE snipe.messages_id_seq OWNER TO postgres;

--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: snipe; Owner: postgres
--

ALTER SEQUENCE snipe.messages_id_seq OWNED BY snipe.messages.id;


--
-- Name: button; Type: TABLE; Schema: ticket; Owner: postgres
--

CREATE TABLE ticket.button (
    identifier text NOT NULL,
    guild_id bigint NOT NULL,
    template text,
    category_id bigint,
    topic text
);


ALTER TABLE ticket.button OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: ticket; Owner: postgres
--

CREATE TABLE ticket.config (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    message_id bigint NOT NULL,
    staff_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    blacklisted_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    channel_name text,
    logging_channel bigint DEFAULT 0
);


ALTER TABLE ticket.config OWNER TO postgres;

--
-- Name: logs; Type: TABLE; Schema: ticket; Owner: postgres
--

CREATE TABLE ticket.logs (
    guild_id bigint,
    channel_id bigint
);


ALTER TABLE ticket.logs OWNER TO postgres;

--
-- Name: open; Type: TABLE; Schema: ticket; Owner: postgres
--

CREATE TABLE ticket.open (
    identifier text NOT NULL,
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    user_id bigint NOT NULL
);


ALTER TABLE ticket.open OWNER TO postgres;

--
-- Name: message; Type: TABLE; Schema: timer; Owner: postgres
--

CREATE TABLE timer.message (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    template text NOT NULL,
    "interval" integer NOT NULL,
    next_trigger timestamp with time zone NOT NULL
);


ALTER TABLE timer.message OWNER TO postgres;

--
-- Name: purge; Type: TABLE; Schema: timer; Owner: postgres
--

CREATE TABLE timer.purge (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    "interval" integer NOT NULL,
    next_trigger timestamp with time zone NOT NULL,
    method text DEFAULT 'bulk'::text NOT NULL
);


ALTER TABLE timer.purge OWNER TO postgres;

--
-- Name: api_sessions; Type: TABLE; Schema: user; Owner: postgres
--

CREATE TABLE "user".api_sessions (
    token text NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    last_used_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    user_agent text,
    ip_address inet
);


ALTER TABLE "user".api_sessions OWNER TO postgres;

--
-- Name: oauth_sessions; Type: TABLE; Schema: user; Owner: postgres
--

CREATE TABLE "user".oauth_sessions (
    session_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id bigint NOT NULL,
    access_token text NOT NULL,
    refresh_token text NOT NULL,
    token_type text NOT NULL,
    scope text NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE "user".oauth_sessions OWNER TO postgres;

--
-- Name: settings; Type: TABLE; Schema: user; Owner: postgres
--

CREATE TABLE "user".settings (
    user_id bigint NOT NULL,
    config jsonb DEFAULT '{}'::jsonb,
    prefix character varying(7)
);


ALTER TABLE "user".settings OWNER TO postgres;

--
-- Name: channels; Type: TABLE; Schema: voicemaster; Owner: postgres
--

CREATE TABLE voicemaster.channels (
    guild_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    owner_id bigint
);


ALTER TABLE voicemaster.channels OWNER TO postgres;

--
-- Name: configuration; Type: TABLE; Schema: voicemaster; Owner: postgres
--

CREATE TABLE voicemaster.configuration (
    guild_id bigint NOT NULL,
    category_id bigint,
    interface_id bigint,
    channel_id bigint,
    role_id bigint,
    region text,
    bitrate bigint
);


ALTER TABLE voicemaster.configuration OWNER TO postgres;

--
-- Name: config; Type: TABLE; Schema: autopfp; Owner: postgres
--

CREATE TABLE autopfp.config (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    keywords text[] DEFAULT '{}'::text[] NOT NULL,
    channels bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    interval_minutes integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE autopfp.config OWNER TO postgres;

--
-- Name: used_images; Type: TABLE; Schema: autopfp; Owner: postgres
--

CREATE TABLE autopfp.used_images (
    guild_id bigint NOT NULL,
    user_id bigint NOT NULL,
    image_url text NOT NULL,
    used_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE autopfp.used_images OWNER TO postgres;

--
-- Name: job_applications id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_applications ALTER COLUMN id SET DEFAULT nextval('public.job_applications_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: logging_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logging_history ALTER COLUMN id SET DEFAULT nextval('public.logging_history_id_seq'::regclass);


--
-- Name: properties id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties ALTER COLUMN id SET DEFAULT nextval('public.properties_id_seq'::regclass);


--
-- Name: user_properties id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_properties ALTER COLUMN id SET DEFAULT nextval('public.user_properties_id_seq'::regclass);


--
-- Name: vesta_businesses id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vesta_businesses ALTER COLUMN id SET DEFAULT nextval('public.businesses_id_seq'::regclass);


--
-- Name: whitelist id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.whitelist ALTER COLUMN id SET DEFAULT nextval('public.whitelist_id_seq'::regclass);


--
-- Name: edits id; Type: DEFAULT; Schema: snipe; Owner: postgres
--

ALTER TABLE ONLY snipe.edits ALTER COLUMN id SET DEFAULT nextval('snipe.edits_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: snipe; Owner: postgres
--

ALTER TABLE ONLY snipe.messages ALTER COLUMN id SET DEFAULT nextval('snipe.messages_id_seq'::regclass);


--
-- Name: disabled disabled_pkey; Type: CONSTRAINT; Schema: commands; Owner: postgres
--

ALTER TABLE ONLY commands.disabled
    ADD CONSTRAINT disabled_pkey PRIMARY KEY (guild_id, channel_id, command);


--
-- Name: ignore ignore_pkey; Type: CONSTRAINT; Schema: commands; Owner: postgres
--

ALTER TABLE ONLY commands.ignore
    ADD CONSTRAINT ignore_pkey PRIMARY KEY (guild_id, target_id);


--
-- Name: restricted restricted_pkey; Type: CONSTRAINT; Schema: commands; Owner: postgres
--

ALTER TABLE ONLY commands.restricted
    ADD CONSTRAINT restricted_pkey PRIMARY KEY (guild_id, role_id, command);


--
-- Name: config config_guild_id_key; Type: CONSTRAINT; Schema: disboard; Owner: postgres
--

ALTER TABLE ONLY disboard.config
    ADD CONSTRAINT config_guild_id_key UNIQUE (guild_id);


--
-- Name: reminder reminder_pkey; Type: CONSTRAINT; Schema: fortnite; Owner: postgres
--

ALTER TABLE ONLY fortnite.reminder
    ADD CONSTRAINT reminder_pkey PRIMARY KEY (user_id, item_id);


--
-- Name: rotation rotation_guild_id_key; Type: CONSTRAINT; Schema: fortnite; Owner: postgres
--

ALTER TABLE ONLY fortnite.rotation
    ADD CONSTRAINT rotation_guild_id_key UNIQUE (guild_id);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: guild; Owner: postgres
--

ALTER TABLE ONLY guild.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (guild_id);


--
-- Name: config config_pkey; Type: CONSTRAINT; Schema: jail; Owner: postgres
--

ALTER TABLE ONLY jail.config
    ADD CONSTRAINT config_pkey PRIMARY KEY (guild_id);


--
-- Name: restore_roles restore_roles_pkey; Type: CONSTRAINT; Schema: jail; Owner: postgres
--

ALTER TABLE ONLY jail.restore_roles
    ADD CONSTRAINT restore_roles_pkey PRIMARY KEY (user_id, guild_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: jail; Owner: postgres
--

ALTER TABLE ONLY jail.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id, guild_id);


--
-- Name: config config_pkey; Type: CONSTRAINT; Schema: joindm; Owner: postgres
--

ALTER TABLE ONLY joindm.config
    ADD CONSTRAINT config_pkey PRIMARY KEY (guild_id);


--
-- Name: albums albums_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.albums
    ADD CONSTRAINT albums_pkey PRIMARY KEY (user_id, artist, album);


--
-- Name: artists artists_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.artists
    ADD CONSTRAINT artists_pkey PRIMARY KEY (user_id, artist);


--
-- Name: config config_user_id_key; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.config
    ADD CONSTRAINT config_user_id_key UNIQUE (user_id);


--
-- Name: crown_updates crown_updates_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.crown_updates
    ADD CONSTRAINT crown_updates_pkey PRIMARY KEY (guild_id);


--
-- Name: crowns crowns_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.crowns
    ADD CONSTRAINT crowns_pkey PRIMARY KEY (guild_id, artist);


--
-- Name: hidden hidden_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.hidden
    ADD CONSTRAINT hidden_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: tracks tracks_pkey; Type: CONSTRAINT; Schema: lastfm; Owner: postgres
--

ALTER TABLE ONLY lastfm.tracks
    ADD CONSTRAINT tracks_pkey PRIMARY KEY (user_id, artist, track);


--
-- Name: config config_guild_id_key; Type: CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.config
    ADD CONSTRAINT config_guild_id_key UNIQUE (guild_id);


--
-- Name: member member_pkey; Type: CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.member
    ADD CONSTRAINT member_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: notification notification_pkey; Type: CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.notification
    ADD CONSTRAINT notification_pkey PRIMARY KEY (guild_id);


--
-- Name: role role_pkey; Type: CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.role
    ADD CONSTRAINT role_pkey PRIMARY KEY (guild_id, level);


--
-- Name: role role_role_id_key; Type: CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.role
    ADD CONSTRAINT role_role_id_key UNIQUE (role_id);


--
-- Name: config config_pkey; Type: CONSTRAINT; Schema: pingonjoin; Owner: postgres
--

ALTER TABLE ONLY pingonjoin.config
    ADD CONSTRAINT config_pkey PRIMARY KEY (guild_id);


--
-- Name: afk afk_user_id_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.afk
    ADD CONSTRAINT afk_user_id_unique UNIQUE (user_id);


--
-- Name: aliases aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.aliases
    ADD CONSTRAINT aliases_pkey PRIMARY KEY (guild_id, name);


--
-- Name: antinuke2 antinuke2_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.antinuke2
    ADD CONSTRAINT antinuke2_pkey PRIMARY KEY (guild_id);


--
-- Name: antiraid antiraid_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.antiraid
    ADD CONSTRAINT antiraid_pkey PRIMARY KEY (guild_id);


--
-- Name: auto_role auto_role_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auto_role
    ADD CONSTRAINT auto_role_pkey PRIMARY KEY (guild_id, role_id, action);


--
-- Name: blacklist blacklist_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.blacklist
    ADD CONSTRAINT blacklist_user_id_key UNIQUE (user_id);


--
-- Name: blunt blunt_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.blunt
    ADD CONSTRAINT blunt_pkey PRIMARY KEY (guild_id);


--
-- Name: boost_history boost_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.boost_history
    ADD CONSTRAINT boost_history_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: boost_message boost_message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.boost_message
    ADD CONSTRAINT boost_message_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: booster_role booster_role_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booster_role
    ADD CONSTRAINT booster_role_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: counter counter_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.counter
    ADD CONSTRAINT counter_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: fake_permissions fake_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fake_permissions
    ADD CONSTRAINT fake_permissions_pkey PRIMARY KEY (guild_id, role_id, permission);


--
-- Name: forcenick forcenick_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.forcenick
    ADD CONSTRAINT forcenick_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: gallery gallery_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gallery
    ADD CONSTRAINT gallery_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: giveaway_entries giveaway_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.giveaway_entries
    ADD CONSTRAINT giveaway_entries_pkey PRIMARY KEY (message_id, user_id);


--
-- Name: gnames gnames_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gnames
    ADD CONSTRAINT gnames_pkey PRIMARY KEY (guild_id, name, changed_at);


--
-- Name: goodbye_message goodbye_message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goodbye_message
    ADD CONSTRAINT goodbye_message_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: guildblacklist guildblacklist_guild_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.guildblacklist
    ADD CONSTRAINT guildblacklist_guild_id_key UNIQUE (guild_id);


--
-- Name: ignored_logging ignored_logging_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ignored_logging
    ADD CONSTRAINT ignored_logging_pkey PRIMARY KEY (guild_id, target_id);


--
-- Name: jail jail_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.jail
    ADD CONSTRAINT jail_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: job_applications job_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_applications
    ADD CONSTRAINT job_applications_pkey PRIMARY KEY (id);


--
-- Name: job_applications job_applications_user_id_guild_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_applications
    ADD CONSTRAINT job_applications_user_id_guild_id_key UNIQUE (user_id, guild_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: logging_history logging_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logging_history
    ADD CONSTRAINT logging_history_pkey PRIMARY KEY (id);


--
-- Name: logging logging_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logging
    ADD CONSTRAINT logging_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: marriages marriages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.marriages
    ADD CONSTRAINT marriages_pkey PRIMARY KEY (user_id);


--
-- Name: moderation moderation_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.moderation
    ADD CONSTRAINT moderation_pkey PRIMARY KEY (guild_id);


--
-- Name: pagination pagination_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pagination
    ADD CONSTRAINT pagination_pkey PRIMARY KEY (guild_id, message_id, channel_id);


--
-- Name: prefix prefix_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.prefix
    ADD CONSTRAINT prefix_pkey PRIMARY KEY (guild_id);


--
-- Name: properties properties_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_name_key UNIQUE (name);


--
-- Name: properties properties_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_pkey PRIMARY KEY (id);


--
-- Name: publisher publisher_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.publisher
    ADD CONSTRAINT publisher_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: reaction_role reaction_role_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reaction_role
    ADD CONSTRAINT reaction_role_pkey PRIMARY KEY (guild_id, message_id, emoji);


--
-- Name: reaction_trigger reaction_trigger_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reaction_trigger
    ADD CONSTRAINT reaction_trigger_pkey PRIMARY KEY (guild_id, trigger, emoji);


--
-- Name: response_trigger response_trigger_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.response_trigger
    ADD CONSTRAINT response_trigger_pkey PRIMARY KEY (guild_id, trigger);


--
-- Name: role_restore role_restore_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.role_restore
    ADD CONSTRAINT role_restore_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: roleplay roleplay_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.roleplay
    ADD CONSTRAINT roleplay_pkey PRIMARY KEY (user_id, target_id, category);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (guild_id);


--
-- Name: skullboard skullboard_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.skullboard
    ADD CONSTRAINT skullboard_pkey PRIMARY KEY (guild_id);


--
-- Name: skullboardmes skullboardmes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.skullboardmes
    ADD CONSTRAINT skullboardmes_pkey PRIMARY KEY (guild_id, channel_message_id, message_id);


--
-- Name: starboard_entry starboard_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.starboard_entry
    ADD CONSTRAINT starboard_entry_pkey PRIMARY KEY (guild_id, channel_id, message_id, emoji);


--
-- Name: starboard starboard_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.starboard
    ADD CONSTRAINT starboard_pkey PRIMARY KEY (guild_id, emoji);


--
-- Name: sticky_message sticky_message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sticky_message
    ADD CONSTRAINT sticky_message_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: tag_aliases tag_aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tag_aliases
    ADD CONSTRAINT tag_aliases_pkey PRIMARY KEY (guild_id, alias);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (guild_id, name);


--
-- Name: thread thread_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.thread
    ADD CONSTRAINT thread_pkey PRIMARY KEY (guild_id, thread_id);


--
-- Name: roleplay_enabled unique_guild_id; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.roleplay_enabled
    ADD CONSTRAINT unique_guild_id UNIQUE (guild_id);


--
-- Name: user_properties user_properties_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_properties
    ADD CONSTRAINT user_properties_pkey PRIMARY KEY (id);


--
-- Name: user_properties user_properties_user_id_property_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_properties
    ADD CONSTRAINT user_properties_user_id_property_id_key UNIQUE (user_id, property_id);


--
-- Name: vape vape_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vape
    ADD CONSTRAINT vape_pkey PRIMARY KEY (user_id);


--
-- Name: vesta_businesses vesta_businesses_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vesta_businesses
    ADD CONSTRAINT vesta_businesses_pkey PRIMARY KEY (id);


--
-- Name: vesta_economy vesta_economy_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vesta_economy
    ADD CONSTRAINT vesta_economy_pkey PRIMARY KEY (user_id);


--
-- Name: webhook webhook_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.webhook
    ADD CONSTRAINT webhook_pkey PRIMARY KEY (channel_id, webhook_id);


--
-- Name: welcome_message welcome_message_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.welcome_message
    ADD CONSTRAINT welcome_message_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: whitelist whitelist_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.whitelist
    ADD CONSTRAINT whitelist_pkey PRIMARY KEY (id);


--
-- Name: workers workers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workers
    ADD CONSTRAINT workers_pkey PRIMARY KEY (user_id, guild_id);


--
-- Name: edits edits_pkey; Type: CONSTRAINT; Schema: snipe; Owner: postgres
--

ALTER TABLE ONLY snipe.edits
    ADD CONSTRAINT edits_pkey PRIMARY KEY (id);


--
-- Name: ignore ignore_pkey; Type: CONSTRAINT; Schema: snipe; Owner: postgres
--

ALTER TABLE ONLY snipe.ignore
    ADD CONSTRAINT ignore_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: snipe; Owner: postgres
--

ALTER TABLE ONLY snipe.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: button button_pkey; Type: CONSTRAINT; Schema: ticket; Owner: postgres
--

ALTER TABLE ONLY ticket.button
    ADD CONSTRAINT button_pkey PRIMARY KEY (identifier, guild_id);


--
-- Name: config config_guild_id_key; Type: CONSTRAINT; Schema: ticket; Owner: postgres
--

ALTER TABLE ONLY ticket.config
    ADD CONSTRAINT config_guild_id_key UNIQUE (guild_id);


--
-- Name: open open_pkey; Type: CONSTRAINT; Schema: ticket; Owner: postgres
--

ALTER TABLE ONLY ticket.open
    ADD CONSTRAINT open_pkey PRIMARY KEY (identifier, guild_id, user_id);


--
-- Name: logs unique_guild_id; Type: CONSTRAINT; Schema: ticket; Owner: postgres
--

ALTER TABLE ONLY ticket.logs
    ADD CONSTRAINT unique_guild_id UNIQUE (guild_id);


--
-- Name: message message_pkey; Type: CONSTRAINT; Schema: timer; Owner: postgres
--

ALTER TABLE ONLY timer.message
    ADD CONSTRAINT message_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: purge purge_pkey; Type: CONSTRAINT; Schema: timer; Owner: postgres
--

ALTER TABLE ONLY timer.purge
    ADD CONSTRAINT purge_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: api_sessions api_sessions_pkey; Type: CONSTRAINT; Schema: user; Owner: postgres
--

ALTER TABLE ONLY "user".api_sessions
    ADD CONSTRAINT api_sessions_pkey PRIMARY KEY (token);


--
-- Name: oauth_sessions oauth_sessions_pkey; Type: CONSTRAINT; Schema: user; Owner: postgres
--

ALTER TABLE ONLY "user".oauth_sessions
    ADD CONSTRAINT oauth_sessions_pkey PRIMARY KEY (session_id);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: user; Owner: postgres
--

ALTER TABLE ONLY "user".settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (user_id);


--
-- Name: channels channels_pkey; Type: CONSTRAINT; Schema: voicemaster; Owner: postgres
--

ALTER TABLE ONLY voicemaster.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (guild_id, channel_id);


--
-- Name: configuration configuration_pkey; Type: CONSTRAINT; Schema: voicemaster; Owner: postgres
--

ALTER TABLE ONLY voicemaster.configuration
    ADD CONSTRAINT configuration_pkey PRIMARY KEY (guild_id);


--
-- Name: config config_pkey; Type: CONSTRAINT; Schema: autopfp; Owner: postgres
--

ALTER TABLE ONLY autopfp.config
    ADD CONSTRAINT config_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: used_images used_images_pkey; Type: CONSTRAINT; Schema: autopfp; Owner: postgres
--

ALTER TABLE ONLY autopfp.used_images
    ADD CONSTRAINT used_images_pkey PRIMARY KEY (guild_id, user_id, image_url);


--
-- Name: whitelist_guild_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX whitelist_guild_id_idx ON public.whitelist USING btree (guild_id) WHERE (user_id IS NULL);


--
-- Name: whitelist_guild_id_user_id_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX whitelist_guild_id_user_id_idx ON public.whitelist USING btree (guild_id, user_id) WHERE (user_id IS NOT NULL);


--
-- Name: api_sessions_expires_at_idx; Type: INDEX; Schema: user; Owner: postgres
--

CREATE INDEX api_sessions_expires_at_idx ON "user".api_sessions USING btree (expires_at);


--
-- Name: api_sessions_user_id_idx; Type: INDEX; Schema: user; Owner: postgres
--

CREATE INDEX api_sessions_user_id_idx ON "user".api_sessions USING btree (user_id);


--
-- Name: oauth_sessions_expires_at_idx; Type: INDEX; Schema: user; Owner: postgres
--

CREATE INDEX oauth_sessions_expires_at_idx ON "user".oauth_sessions USING btree (expires_at);


--
-- Name: oauth_sessions_user_id_idx; Type: INDEX; Schema: user; Owner: postgres
--

CREATE INDEX oauth_sessions_user_id_idx ON "user".oauth_sessions USING btree (user_id);


--
-- Name: config config_guild_id_fkey; Type: FK CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.config
    ADD CONSTRAINT config_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES public.settings(guild_id) ON DELETE CASCADE;


--
-- Name: member member_guild_id_fkey; Type: FK CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.member
    ADD CONSTRAINT member_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES level.config(guild_id) ON DELETE CASCADE;


--
-- Name: notification notification_guild_id_fkey; Type: FK CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.notification
    ADD CONSTRAINT notification_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES level.config(guild_id) ON DELETE CASCADE;


--
-- Name: role role_guild_id_fkey; Type: FK CONSTRAINT; Schema: level; Owner: postgres
--

ALTER TABLE ONLY level.role
    ADD CONSTRAINT role_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES level.config(guild_id) ON DELETE CASCADE;


--
-- Name: jobs jobs_business_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.vesta_businesses(id);


--
-- Name: starboard_entry starboard_entry_guild_id_emoji_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.starboard_entry
    ADD CONSTRAINT starboard_entry_guild_id_emoji_fkey FOREIGN KEY (guild_id, emoji) REFERENCES public.starboard(guild_id, emoji) ON DELETE CASCADE;


--
-- Name: tag_aliases tag_aliases_guild_id_original_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tag_aliases
    ADD CONSTRAINT tag_aliases_guild_id_original_fkey FOREIGN KEY (guild_id, original) REFERENCES public.tags(guild_id, name) ON DELETE CASCADE;


--
-- Name: user_properties user_properties_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_properties
    ADD CONSTRAINT user_properties_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(id) ON DELETE CASCADE;


--
-- Name: workers workers_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.workers
    ADD CONSTRAINT workers_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id);


--
-- Name: button button_guild_id_fkey; Type: FK CONSTRAINT; Schema: ticket; Owner: postgres
--

ALTER TABLE ONLY ticket.button
    ADD CONSTRAINT button_guild_id_fkey FOREIGN KEY (guild_id) REFERENCES ticket.config(guild_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

