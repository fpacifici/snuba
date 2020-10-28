<img src="/snuba/web/static/img/snuba.svg" width="150" height="71"/>

A service providing fast event searching, filtering and aggregation on arbitrary fields.



## Sentry + Snuba

Add/change the following lines in `~/.sentry/sentry.conf.py`:

    SENTRY_SEARCH = 'sentry.search.snuba.EventsDatasetSnubaSearchBackend'
    SENTRY_TSDB = 'sentry.tsdb.redissnuba.RedisSnubaTSDB'
    SENTRY_EVENTSTREAM = 'sentry.eventstream.snuba.SnubaEventStream'

Run:

    sentry devservices up

Access raw clickhouse client (similar to psql):

    docker exec -it sentry_clickhouse clickhouse-client

Data is written into the table `sentry_local`: `select count() from sentry_local;`

## Requirements (Only required if you are developing against Snuba)

Snuba assumes:

1. A Clickhouse server endpoint at `CLICKHOUSE_HOST` (default `localhost`).
2. A redis instance running at `REDIS_HOST` (default `localhost`). On port
   `6379`

A quick way to get these services running is to set up sentry, then use:

    sentry devservices up --exclude=snuba

Note that Snuba assumes that everything is running on UTC time. Otherwise you may experience issues with timezone mismatches.

## Install / Run (Only required if you are developing against Snuba)

    mkvirtualenv snuba --python=python3.7
    workon snuba
    make install-python-dependencies
    make setup-git

    # Run API server
    snuba api

## API

Snuba exposes an HTTP API (default port: `1218`) with the following endpoints.

- [/](/): Shows this page.
- [/dashboard](/dashboard): Query dashboard
- [/query](/query): Endpoint for querying clickhouse.
- [/config](/config): Console for runtime config options

## Settings

Settings are found in `settings.py`

- `CLUSTERS` : Provides the list of clusters and the hostname, port, and storage sets that should run on each cluster. Local vs distributed is also set per cluster.
- `REDIS_HOST` : The host redis is running on.

## Tests

    pip install -e .
    make test

## Testing Against Sentry

```
workon snuba
git checkout your-snuba-branch
snuba api
```
And then in another terminal
```
workon sentry
git checkout master
git pull
sentry devservices up --exclude=snuba
```
This will get the most recent version of Sentry on master, and bring up all snuba's dependencies.

You will want to run the following Sentry tests:
```
USE_SNUBA=1 make test-acceptance
USE_SNUBA=1 make test-snuba
make test-python
```
Note that python tests do not currently pass with the `USE_SNUBA` flag, but should be fixed in the future. For now, simply run it without `USE_SNUBA` flag (which determines the version of TagStore). Note also that we check for the existance of `USE_SNUBA` rather than take into account the value. `USE_SNUBA=0` does not currently work as intended.

## Querying

Try out queries on the [query console](/query). Queries are submitted as a JSON
body to the [/query](/query) endpoint.

### The Query Payload

An example query body might look like:

    {
        "project":[1,2],
        "selected_columns": ["tags[environment]"],
        "aggregations": [
            ["max", "received", "last_seen"]
        ],
        "conditions": [
            ["tags[environment]", "=", "prod"]
        ],
        "from_date": "2011-07-01T19:54:15",
        "to_date": "2018-07-06T19:54:15"
        "granularity": 3600,
        "groupby": ["group_id", "time"],
        "having": [],
        "issues": [],
    }

#### selected_columns, groupby

`groupby` is a list of columns (or column aliases) that will be translated into
a SQL `GROUP BY` clause. These columns are automatically included in the query
output.  `selected_columns` is a list of additional columns that should be added
to the `SELECT` clause.

Trying to use both of these in the same query will probably result in an invalid
query, as you cannot select a bare column, while grouping by another column, as
the value of the extra selected column for a given output row (group) would be
ambiguous.

#### aggregations

This is an array of 3-tuples of the form:

    [function, column, alias]

which is transformed into the SQL:

    function(column) AS alias

Some aggregation function are generated by other functions, eg topK. so an
example query would send:

    ["top5", "environment", "top_five_envs"]

To produce the SQL:

    topK(5)(environment) AS top_five_envs

Count is a somewhat special case, it doesn't have a column argument, and is
specified as "count()", not "count".

    ["count()", null, "item_count"]

Aggregations are also included in the output columns automatically.


#### conditions

Conditions are used to construct the WHERE clause, and consist of an
array of 3-tuples (in their most basic form):

    [column_name, operation, literal]

Valid operations:

    ['>', '<', '>=', '<=', '=', '!=', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL', 'LIKE', 'NOT LIKE'],

For example:

    [
        ['platform', '=', 'python'],
    ]

    platform = 'python'

Top-level sibling conditions are `AND`ed together:

    [
        ['w', '=', '1'],
        ['x', '=', '2'],
    ]

    w = '1' AND x = '2'

The first position (column_name) can be replaced with an array that
represents a function call. The first item is a function name, and nested
arrays represent the arguments supplied to the preceding function:

    [
        [['fn1', []], '=', '1'],
    ]

    fn1() = '1'

Multiple arguments can be provided:

    [
        [['fn2', ['arg', 'arg']], '=', '2'],
    ]

    fn2(arg, arg) = '2'

Function calls can be nested:

    [
        [['fn3', ['fn4', ['arg']]], '=', '3'],
    ]

    fn3(fn4(arg)) = '3'

An alias can be provided at the end of the top-level function array. This
alias can then be used elsewhere in the query, such as `selected_columns`:

    [
        [['fn1', [], 'alias'], '=', '1'],
    ]

    (fn1() AS alias) = '1'

To do an `OR`, nest the array one level deeper:

    [
        [
            ['w', '=', '1'],
            ['x', '=', '2'],
        ],
    ]

    (w = '1' OR x = '2')

Sibling arrays at the second level are `AND`ed (note this is the same
as the simpler `AND` above):

    [
        [
            ['w', '=', '1'],
        ],
        [
            ['x', '=', '2'],
        ],
    ]

    (w = '1' AND x = '2')

And these two can be combined to mix `OR` and `AND`:

    [
        [
            ['w', '=', '1'], ['x', '=', '2']
        ],
        [
            ['y', '=', '3'], ['z', '=', '4']
        ],
    ]

    (w = '1' OR x = '2') AND (y = '3' OR z = '4')

#### from_date / to_date

#### granularity

Snuba provides a magic column `time`, that you can use in groupby or filter
expressions. This column gives a floored time value for each event so that
events in the same minute/hour/day/etc. can be grouped.

`granularity` determines the number of seconds in each of these time buckets.
Eg, to count the number of events by hour, you would do

    {
        "aggregations": [["count()", "", "event_count"]],
        "granularity": 3600,
        "groupby": "time"
    }

#### having

#### issues

#### project

#### sample

Sample is a numeric value. If it is < 1, then it is interpreted to mean "read
this percentage of rows". eg.

    "sample": 0.5

Will read 50% of all rows.

If it is > 1, it means "read up to this number of rows", eg.

    "sample": 1000

Will read 1000 rows maximum, and then return a result.

Note that sampling does not do any adjustment/correction of aggregates. so if
you do a count() with 10% sampling, you should multiply the results by 10 to
get an approximate value for the 'real' count. For sample > 1 you cannot do
this adjustment as there is no way to tell what percentage of rows were read.
For other aggregations like uniq(), min(), max(), there is no adjustment you
can do, the results will simply deviate more and more from the real value in an
unpredictable way as the sampling rate approaches 0.

Queries with sampling are stable. Ie the same query with the same sampling
factor over the same data should consistently return the exact same result.


### Groups / Issues

Snuba provides a magic column `group_id` that can be used to group events by issue.

Because events can be reassigned to different issues through merging, and
because snuba does not support updates, we cannot store the issue id for an
event in snuba. If you want to filter or group by `group_id`, you need to pass a
list of `group_ids` into the query.  This list is a mapping from issue ids to the
event `primary_hash`es in that issue. Snuba automatically expands this mapping
into the query so that filters/grouping on `group_id` will just work.

### Tags

Event tags are stored in one of 2 ways. Promoted tags are the ones we expect to
be queried often and as such are stored as top level columns. The list of
promoted tag columns is defined in settings and is somewhat fixed in the
schema. The rest of an event's tags are stored as a key-value map.  In practice
this is implemented as 2 columns of type Array(String), called `tags.key` and
`tags.value`

The snuba service provides 2 mechanisms for abstracting this tiered tag
structure by providing some special columns that will be resolved to the
correct SQL expression for the type of tag. These mechanisms should generally
not be used in conjunction with each other.

#### When you know the names of the tags you want.

You can use the `tags[name]` anywhere you would use a normal column name in an
expression, and it will resolve to the value of the tag with `name`, regardless
of whether that tag is promoted or not. Use this syntax when you are looking
for a specific named tag. eg.

    # Find all events in production with user_custom_key defined.
    "conditions": [
        ["tags[environment]", "=", "prod"],
        ["tags[custom_user_tag]", "IS NOT NULL"]
    ],
<!-- -->

    # Find the number of unique environments
    "aggregations": [
        ["uniq", "tags[environment]", "unique_envs"],
    ],

#### When you don't know the name, or want to query all tags.

These are virtual columns that can be used to get results when the names of the
tags are not explicitly known. Using `tags_key` or `tags_value` in an
expression will expand all of the promoted and non-promoted tags so that there
is one row per tag (an array-join in Clickhouse terms). For each row, the name
of the tag will be in the `tags_key` column, and the value in the `tags_value`
column.

    # Find the top 5 most often used tags
    "aggregations": [
        ["top5", "tags_key", "top_tag_keys"],
    ],
<!-- -->

    # Find any tags whose *value* is `bar`
    "conditions": [
        ["tags_value", "=", "bar"],
    ],


Note, when using this expression. the thing you are counting is tags, not events, so if you
have 10 events, each of which has 10 tags, then a `count()` of `tags_key` will return 100.


##  Migrations

Snuba provides functionality to manage ClickHouse database migrations. Migrations
in Snuba are organized into groups, which typically correspond with features / sets
of related tables in Snuba. In some cases, groups can provide a mechanism to test
experimental features in Snuba that should not be rolled out to most users yet.
Migration groups can be defined as either optional or mandatory. Optional groups
can be toggled by the user via `settings.SKIPPED_MIGRATION_GROUPS`. In most cases,
the default in settings.py should not be changed, and doing so may result in
unexpected behavior.


### Commands
The `snuba migrations` group of commands provides some functions to manage migrations.

#### List migrations
`snuba migrations list`

- Lists all migrations and their statuses

#### Run all migrations
`snuba migrations migrate --force`

- Runs all pending migrations and brings your database to the latest state.
- Running with the --force flag means that any migrations marked blocking (generally
because they contain a data migration) will also be executed. Blocking migrations may
take some time to complete. Running with --force assumes that any consumers filling
the corresponding table are stopped and no new data is being written to the table
as the migration is taking place.
- Running this without the --force flag, will only execute the migrations if none
are blocking.
- If you are running `snuba devserver`, this command automatically run when the
devserver is started and there is no need to manage migrations manually.

#### Run a single migration
`snuba migrations run --group <group> --migration-id <migration_id>`

- Runs a single migration
- Only allowed if there are no prior migrations in that group that have not been completed

#### Reverse a single migration
`snuba migrations reverse --group <group> --migration-id <migration_id>`

- Reverses a single migration
- Only allowed if there are no subsequent completed migrations in that group


### Add a new migration
In order to add a new migration, first determine which migration group the new
migration should be added to, and add an entry to that group in `migrations/groups.py`
with the new migration identifier you have chosen. By convention we prefix migration
IDs with a number matching the position of the migration in the group, i.e. the 4th
migration in that group will be prefixed with `0004_`. Add a file which will contain
the new migration at `/migrations/snuba_migrations/<group>/<migration_id>.py`.

If you need to create a new group, add the group to `migrations.groups.MigrationGroup`
and a loader for the group defining the path to the directory where that group's
migrations will be located. Register these to `migrations.groups._REGISTERED_GROUPS` -
note the position of the group in this list determines the order the migrations
will be executed in.

The new migration should contain a class called `Migration` which inherits from
`MultiStepMigration`. You should define all four methods - `forwards_local`,
`backwards_local`, `forwards_dist` and `backwards_dist` in order to provide the
DDL for all ClickHouse layouts that a user may have. The operations provided in
the `_local` methods will run on each local ClickHouse node and the `_dist` methods
will run on each distributed ClickHouse nodes (if any).

For each forwards method, you should provide the sequence of operations to be run
on that node. In case the forwards methods fail halfway, the corresponding backwards
methods should also restore the original state so the migration can be retried.
For example if a temporary table is created during the forwards migration, the backwards
migration should drop it.

A migration that can not immediately complete (i.e. requires data to be rewritten)
should be marked as blocking. Typically this indicates that the migration needs to
be run with the relevant consumer stopped or an alternate strategy (e.g. dual writing)
employed to ensure no downtime as the migration is running.
