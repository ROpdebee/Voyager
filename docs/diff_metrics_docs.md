# Documentation for the diff metrics

The CSV may contain some empty values for the metrics in some lines. These mean that the metrics could not be calculated for that change, most likely due to parsing errors because the role isn't valid in the current Ansible version (e.g., removed syntax features). It might be a good idea to check how many of such bumps there are.

v1 and v2 *should* always be a pair of consecutive versions.


## Description of the fields

role id: The ID of the role on Galaxy. Can be used to cross-reference against other tables.

v1: Tag text for what is assumed to be the earlier version.

v2: Tag text for what is assumed to be the later version.


The rest of the fields are the metrics. Their names generally take the following form:
```
<ObjectType><ChangeType>
```

E.g., "TaskAddition", "HandlerTaskEdit" etc.

There are 4 main change types:
- Addition: The addition of an object to the role.
- Removal: The removal of an object from the role.
- Edit: A change to the contents of an object (NOTE: If the object is a container, a change to its contents isn't propagated to the container itself. See below.)
- Relocation: A relocation of an object to a new parent, or a new position in a container. This cuts down on many Addition/Deletion pairs.

There are 11 object types:
- DefaultVariable, ConstantVariable: A variable present in either `defaults/\*.yml` or `vars/\*.yml`, respectively.
- DefaultsFile, ConstantsFile: A file present in either `defaults/\*.yml` or `vars/\*.yml`, respectively. They are containers of variables. A role can have multiple of these files.
- MetaFile: The meta/main.yml file. This is not used in any change types, although its contents are.
- Task/HandlerTask: A task in `tasks/\*.yml` or `handlers/\*.yml`, always contained inside of the block of the respective type.
- Block/HandlerBlock: A block in `tasks/\*.yml` or `handlers/\*.yml`, either contained in a file or in another block. Contains tasks and other blocks.
- TasksFile/HandlersFile: A file containing blocks, present in either `tasks/\*.yml` or `handlers/\*.yml`.

Some object type / change type combinations don't make sense, and are not included.

## Change types in more detail

### Variable changes
Change types: `ConstantVariableEdit`, `ConstantVariableRelocation`,  `ConstantVariableRemoval`, `DefaultVariableEdit`, `DefaultVariableRelocation`, `DefaultVariableRemoval`.

#### Additions
`ConstantVariableAddition`, `DefaultVariableAddition`

Used when a variable is completely new to the role, i.e., there is no variable in v1 with a matching name.

#### Removals
`ConstantVariableRemoval`, `DefaultVariableRemoval`

Used when a variable is completely removed from the role, i.e., there is no variable in v2 with a matching name.

#### Edits
`ConstantVariableEdit`, `DefaultVariableEdit`

Used when both v1 and v2 contain the same variable (possibly relocated, see below) but the value given to the variable is different.

#### Relocations
`ConstantVariableRelocation`, `DefaultVariableRelocation`

Used when both v1 and v2 contain the same variable, possibly with a different value (modelled separately as an edit), but the variables
are in a different file (but still in the same component, i.e. defaults only match with defaults). The relocation is then from the file in v1 to the file in v2.


### Variable file changes

#### Addition
`ConstantsFileAddition`, `DefaultsFileAddition`

When a new file has been added to the `vars/` or `defaults/` directory in version v2. Variables contained within this file are diffed separately, leading to new changes. In other words, new variables in this new file will be modelled separately as variable additions. Variables from existing files could have been relocated to this new file, leading to a relocation and potentially an edit.

#### Removal
`ConstantsFileRemoval`, `DefaultsFileRemoval`

When a file has been removed from the `vars/` or `defaults/` directory in version v1. This also leads to new changes for contained variables analogously to variable file additions.

### Relocation
`ConstantsFileRelocation`, `DefaultsFileRelocation`

When a path of a variable file has been changed between v1 and v2 (potentially moved to or from a subdirectory). The contained variables are **NOT** relocated separately, unless another change has taken place.

### Block and task changes

#### Addition
BlockAddition, HandlerBlockAddition, TaskAddition, HandlerTaskAddition

When a new block or task was added to the role. In case of blocks, the contained tasks will either be added or relocated from an existing block.

#### Removal
Analogous to addition.

#### Relocation
For tasks: Used when a task has changed position, either inside of the same block, or to another block. In case a new task was inserted in the block, any task that comes after the inserted task in the changed block will have a relocation as well.

Blocks: analogous.

NOTE: If the parent of the object was relocated, and the object itself wasn't relocated in this same parent, no change for this object will be reported.

#### Task Edits
TaskEdit, HandlerTaskEdit, TaskMiscEdit, HandlerTaskMiscEdit.

Used when the keywords defined on a task have changed. They are further categorized into important edits (TaskEdit, HandlerTaskEdit) or miscellaneous edits (TaskMiscEdit, HandlerTaskMiscEdit) (either or, not both for the same task).

If any of the following keywords are added, removed, or have their value changed, an important edit is given. Otherwise, a miscellaneous edit is reported. An important edit will also represent all edits to miscellaneous keywords. The important keywords represent control flow.

Important keywords:
- loop
- loop_control
- action
- args
- when

#### Block Edits
Used when the non-task-list keywords of a block have changed. This doesn't include the keywords that give the tasks present in a block ("block:", "rescue:", "always:"), these are instead represented as task changes.

NOTE: If a task inside a block is changed, **NO** change is reported for the block itself.

#### Tasks file changes
These are analogous to variable files.


### Metadata changes

#### Dependencies
DependencyAddition, DependencyRemoval

Used when a dependency is added or removed from the role.


#### Platforms
PlatformAddition, PlatformRemoval

Used when a supported platform is added or removed from the role metadata.

#### Miscellaneous
MetaEdit

Used when another change to the metadata has taken place.
